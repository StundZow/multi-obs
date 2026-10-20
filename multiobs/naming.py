"""Nom des fichiers d'enregistrement : NOM-TYPE-VIDEO-DATE, appliqué à toutes les instances."""
import re
import time
import unicodedata

# Types d'enregistrement par défaut (modifiables dans les paramètres) : (clé du nom de fichier, libellé).
DEFAULT_REC_TYPES = [("cam", "Cam"), ("ecran", "Écran"), ("live", "Live")]
DEFAULT_TEMPLATE = "{user}-{type}-{video}-{date}_{time}"

# Équivalents des marqueurs de date d'OBS, pour l'aperçu.
_OBS_DATE = {"{date}": "%CCYY-%MM-%DD", "{time}": "%hh-%mm-%ss"}


def clean(text: str) -> str:
    """Retire ce qui est interdit dans un nom de fichier (et % qu'OBS interpréterait)."""
    return re.sub(r'[\\/:*?"<>|%]+', "", text).strip()


def type_key(label: str) -> str:
    """Libellé -> clé utilisée dans le nom des fichiers : « Écran » -> « ecran », « Face cam » -> « face-cam »."""
    s = unicodedata.normalize("NFKD", label).encode("ascii", "ignore").decode("ascii").lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "type"


def rec_types(settings: dict | None) -> list[tuple[str, str]]:
    """Types définis par l'utilisateur (ou ceux par défaut)."""
    out = []
    for item in (settings or {}).get("rec_types") or []:
        if isinstance(item, (list, tuple)) and len(item) == 2 and item[0] and item[1]:
            out.append((str(item[0]), str(item[1])))
    return out or list(DEFAULT_REC_TYPES)


def type_label(key: str, settings: dict | None) -> str:
    return dict(rec_types(settings)).get(key, key)


def guess_type(name: str, settings: dict | None = None) -> str:
    """Type le plus probable d'après le nom de l'instance (« Écran 2 » -> écran)."""
    types = rec_types(settings)
    n = type_key(name)
    for key, label in types:
        if key in n or type_key(label) in n:
            return key
    synonyms = {"ecran": ("screen", "desktop", "bureau"), "live": ("stream", "twitch", "direct"),
                "cam": ("webcam", "camera", "face")}
    for key, words in synonyms.items():
        if any(w in n for w in words) and key in dict(types):
            return key
    return types[0][0]


def _collapse(s: str) -> str:
    # Champs vides : « Bernard--2026 » -> « Bernard-2026 ».
    s = re.sub(r"([-_ ])[-_ ]+", r"\1", s)
    return s.strip("-_ ") or "Enregistrement"


def obs_format(template: str, user: str, rec_type: str, video: str, suffix: str = "") -> str:
    """Format passé à OBS (FilenameFormatting) ; OBS remplace la date au début du rec."""
    s = (template or DEFAULT_TEMPLATE)
    s = s.replace("{user}", clean(user)).replace("{type}", rec_type).replace("{video}", clean(video))
    for k, v in _OBS_DATE.items():
        s = s.replace(k, v)
    s = _collapse(s)
    if suffix:
        s += "-" + clean(suffix)
    return s


def preview(template: str, user: str, rec_type: str, video: str, suffix: str = "") -> str:
    fmt = obs_format(template, user, rec_type, video, suffix)
    now = time.localtime()
    repl = {"%CCYY": time.strftime("%Y", now), "%MM": time.strftime("%m", now),
            "%DD": time.strftime("%d", now), "%hh": time.strftime("%H", now),
            "%mm": time.strftime("%M", now), "%ss": time.strftime("%S", now)}
    for k, v in repl.items():
        fmt = fmt.replace(k, v)
    return fmt
