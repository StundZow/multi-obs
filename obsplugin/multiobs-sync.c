/*
 * multiobs-sync : module OBS de Multi OBS, pour aligner les enregistrements à l'image près.
 *
 * Pour chaque image vidéo écrite dans le fichier d'enregistrement, OBS donne l'heure où elle a
 * été rendue (os_gettime_ns, la même horloge pour tous les OBS de la machine) et sa position dans
 * le fichier. origine = heure de rendu - position = l'instant qui correspond au début du fichier.
 * Deux fichiers dont les origines sont égales se superposent image pour image au montage ; une
 * pause enlève du temps et repousse l'origine d'autant.
 *
 * Le module ne fait que lire : Multi OBS demande l'état par obs-websocket (requête « status » du
 * vendeur « multiobs-sync ») et corrige lui-même avec des pauses de quelques images.
 *
 * Licence : GPL-2.0-or-later, comme Multi OBS et OBS.
 */
#include <obs-module.h>
#include <obs-frontend-api.h>
#include <util/platform.h>
#include <windows.h>

#include "obs-websocket-api.h"

#define PLUGIN_VERSION "1.0.0"

typedef void (*packet_cb_t)(obs_output_t *output, struct encoder_packet *pkt, struct encoder_packet_time *t,
			    void *param);
typedef void (*packet_cb_fn)(obs_output_t *output, packet_cb_t cb, void *param);

static obs_module_t *module_pointer;
static packet_cb_fn add_packet_cb;    /* OBS 31 et plus : cherchés à l'exécution, le module se charge partout */
static packet_cb_fn remove_packet_cb;
static obs_websocket_vendor vendor;
static obs_output_t *watched;         /* sortie d'enregistrement suivie (référence gardée) */
static SRWLOCK lock = SRWLOCK_INIT;

static struct {
	long long gen;         /* +1 à chaque démarrage d'enregistrement */
	bool active;
	long long frames;      /* images vidéo envoyées au fichier */
	long long first_cts;   /* heure de rendu de la 1re image du fichier (ns) */
	long long first_origin;
	long long origin;      /* origine la plus récente (la plus grande : les pauses la repoussent) */
	long long last_cts;    /* heure de rendu la plus récente vue */
	long long frame_ns;    /* durée d'une image d'après l'encodeur */
} st;

/* ------------------------------------------------------------------------- */
/* Images envoyées au fichier (thread de l'encodeur : court, sans allocation)  */

static void on_packet(obs_output_t *output, struct encoder_packet *pkt, struct encoder_packet_time *t, void *param)
{
	UNUSED_PARAMETER(output);
	UNUSED_PARAMETER(param);
	if (!pkt || !t || pkt->type != OBS_ENCODER_VIDEO || pkt->track_idx != 0 || pkt->timebase_den <= 0 ||
	    !t->cts)
		return;

	/* pts en 1/timebase_den s ; avec des images B, les paquets arrivent dans l'ordre de décodage,
	 * d'où le maximum : l'origine ne fait qu'augmenter (pauses). */
	long long pos_ns = pkt->pts * 1000000000LL / pkt->timebase_den;
	long long origin = (long long)t->cts - pos_ns;

	AcquireSRWLockExclusive(&lock);
	if (!st.frames) {
		st.first_cts = (long long)t->cts;
		st.first_origin = origin;
		st.origin = origin;
	} else if (origin > st.origin) {
		st.origin = origin;
	}
	if ((long long)t->cts > st.last_cts)
		st.last_cts = (long long)t->cts;
	st.frame_ns = (long long)pkt->timebase_num * 1000000000LL / pkt->timebase_den;
	st.frames++;
	ReleaseSRWLockExclusive(&lock);
}

static void unwatch(void)
{
	if (!watched)
		return;
	if (remove_packet_cb)
		remove_packet_cb(watched, on_packet, NULL);
	obs_output_release(watched);
	watched = NULL;
}

/* ------------------------------------------------------------------------- */
/* Événements de l'interface d'OBS (thread de l'interface)                    */

static void on_frontend_event(enum obs_frontend_event event, void *param)
{
	UNUSED_PARAMETER(param);
	switch (event) {
	case OBS_FRONTEND_EVENT_RECORDING_STARTING: {
		/* Envoyé juste avant le démarrage de la sortie : on s'y branche (elle peut avoir été
		 * recréée depuis le dernier enregistrement, au changement de profil par exemple). */
		unwatch();
		AcquireSRWLockExclusive(&lock);
		long long gen = st.gen + 1;
		memset(&st, 0, sizeof(st));
		st.gen = gen;
		ReleaseSRWLockExclusive(&lock);
		obs_output_t *output = obs_frontend_get_recording_output();
		if (output && add_packet_cb) {
			watched = output;
			add_packet_cb(watched, on_packet, NULL);
		} else if (output) {
			obs_output_release(output);
		}
		break;
	}
	case OBS_FRONTEND_EVENT_RECORDING_STARTED:
		AcquireSRWLockExclusive(&lock);
		st.active = true;
		ReleaseSRWLockExclusive(&lock);
		break;
	case OBS_FRONTEND_EVENT_RECORDING_STOPPED:
		AcquireSRWLockExclusive(&lock);
		st.active = false;
		ReleaseSRWLockExclusive(&lock);
		unwatch();
		break;
	case OBS_FRONTEND_EVENT_EXIT:
		unwatch();
		break;
	default:
		break;
	}
}

/* ------------------------------------------------------------------------- */
/* Requête obs-websocket « status » (vendeur multiobs-sync)                   */

static void status_request(obs_data_t *request, obs_data_t *response, void *param)
{
	UNUSED_PARAMETER(request);
	UNUSED_PARAMETER(param);
	AcquireSRWLockShared(&lock);
	obs_data_set_int(response, "gen", st.gen);
	obs_data_set_bool(response, "active", st.active);
	obs_data_set_int(response, "frames", st.frames);
	obs_data_set_int(response, "first_cts", st.first_cts);
	obs_data_set_int(response, "first_origin", st.first_origin);
	obs_data_set_int(response, "origin", st.origin);
	obs_data_set_int(response, "last_cts", st.last_cts);
	obs_data_set_int(response, "frame_ns", st.frame_ns);
	ReleaseSRWLockShared(&lock);
	obs_data_set_string(response, "plugin", PLUGIN_VERSION);
	obs_data_set_string(response, "obs", obs_get_version_string());
	obs_data_set_bool(response, "supported", add_packet_cb != NULL);
	obs_data_set_int(response, "now", (long long)os_gettime_ns());
}

/* ------------------------------------------------------------------------- */
/* Module                                                                     */

MODULE_EXPORT void obs_module_set_pointer(obs_module_t *module)
{
	module_pointer = module;
}

obs_module_t *obs_current_module(void)
{
	return module_pointer;
}

MODULE_EXPORT uint32_t obs_module_ver(void)
{
	return MAKE_SEMANTIC_VERSION(30, 0, 0);
}

MODULE_EXPORT const char *obs_module_name(void)
{
	return "Multi OBS Sync";
}

MODULE_EXPORT const char *obs_module_description(void)
{
	return "Multi OBS : alignement des enregistrements à l'image près";
}

MODULE_EXPORT bool obs_module_load(void)
{
	HMODULE obs = GetModuleHandleW(L"obs.dll");
	if (obs) {
		add_packet_cb = (packet_cb_fn)GetProcAddress(obs, "obs_output_add_packet_callback");
		remove_packet_cb = (packet_cb_fn)GetProcAddress(obs, "obs_output_remove_packet_callback");
	}
	if (!add_packet_cb || !remove_packet_cb) {
		add_packet_cb = remove_packet_cb = NULL;
		blog(LOG_WARNING, "[multiobs-sync] OBS trop ancien (31 ou plus requis) : alignement indisponible");
	}
	obs_frontend_add_event_callback(on_frontend_event, NULL);
	blog(LOG_INFO, "[multiobs-sync] version " PLUGIN_VERSION " chargée");
	return true;
}

MODULE_EXPORT void obs_module_post_load(void)
{
	vendor = obs_websocket_register_vendor("multiobs-sync");
	if (!vendor || !obs_websocket_vendor_register_request(vendor, "status", status_request, NULL))
		blog(LOG_WARNING, "[multiobs-sync] obs-websocket absent : Multi OBS ne pourra pas lire l'alignement");
}

MODULE_EXPORT void obs_module_unload(void)
{
	obs_frontend_remove_event_callback(on_frontend_event, NULL);
	unwatch();
}
