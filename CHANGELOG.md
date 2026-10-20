# Changelog

Chaque version publiée avec `python release.py X.Y.Z` reprend la section correspondante :
c'est ce texte que Multi OBS affiche quand il propose la mise à jour.

## 1.0.6

- Aperçu : quand la scène n'a pas le même format que la carte, les bandes autour de l'image prennent
  **la couleur de l'instance** au lieu du noir, pour ne plus les confondre avec du vide dans la scène OBS.
- Les badges (REC, VCam active) se placent dans les coins de l'image.

## 1.0.5

- Le bouton qui range une instance dans la barre « Instances réduites » a une icône plus parlante :
  un **œil barré** (« masquer »), à la place du petit trait.

## 1.0.4

- **Réduire une instance** : le bouton **—** en haut de sa carte la range dans la barre
  **« Instances réduites »** en bas (l'OBS du live quand tu ne lives pas…). Les autres cartes prennent la place.
- **« Remettre »** (ou double-clic sur la pastille) la ramène en haut, à sa place parmi les autres.
- Une instance réduite garde son état sous les yeux : Éteinte, Actif, REC avec la durée, VCam allumée, alertes.
  Son aperçu est arrêté (aucune ressource) et **« Tout allumer » la laisse de côté**.
- Caméras virtuelles : la réparation automatique n'abandonne plus après un échec (elle réessaie de plus en
  plus espacé), et « Caméras virtuelles : x/y installées » en bas est remis à jour chaque minute.

## 1.0.3

- **Crée tes propres types d'enregistrement** : Paramètres → Enregistrements → Ajouter, Renommer,
  Supprimer (Cam, Écran et Live par défaut). B-roll n'est plus proposé ; une instance qui l'utilisait le garde.
- **Link** (icône chaîne) remplace la case « Synchro » : une instance liée suit les boutons du haut
  et les raccourcis, une instance déliée reste à part (pratique pour le live).
- **Icône dossier** à droite des boutons de chaque instance : ouvre son dossier d'enregistrement.
- Une instance allumée affiche **« Actif »** (au lieu de « Prête »).
- **Caméras virtuelles plus fiables** : si elles disparaissent de Windows, Multi OBS les remet tout seul
  (au démarrage, puis chaque minute) au lieu d'attendre le prochain allumage des instances.
  « Désinstaller » dans les paramètres est maintenant définitif, jusqu'à « Installer / réparer ».
- **Paramètres en onglets** (Général, Enregistrements, Aperçu, Caméras virtuelles, Raccourcis) :
  la fenêtre tient sur un écran 1080p.
- Le changelog de la fenêtre de mise à jour est lisible (il s'affichait en blanc sur blanc).
- Boutons des instances moins serrés : « Reprendre » n'est plus coupé.

## 1.0.2

- Nouveau type d'enregistrement **Live** (en plus de Cam, Écran et B-roll) pour le nom des fichiers.
- Les raccourcis clavier globaux sont **désactivés par défaut** (à activer dans les paramètres).
- En venant de la 1.0.0 / 1.0.1, les réglages restés sur les anciens défauts passent aux nouveaux
  (aperçu 60 i/s en 1/4, identique en arrière-plan, raccourcis désactivés). Tes choix perso sont gardés.
- Fermeture de Multi OBS avec des instances allumées : case **« Se souvenir de mon choix »**, et réglage
  « À la fermeture de Multi OBS » dans les paramètres (Demander / Laisser tourner / Tout éteindre).
- Installateur : options **Ajouter au menu Démarrer** et **Raccourci sur le bureau** (cochées par défaut).
  Corrige les raccourcis qui n'étaient pas créés en 1.0.0 / 1.0.1.
- Quand une caméra virtuelle est éteinte, son image d'attente prend **la couleur de son instance**
  (dans Discord, OBS…). Redémarre l'appli qui l'affiche pour voir la nouvelle image.

## 1.0.1

- **Un seul fichier à télécharger** : l'installateur contient Multi OBS. Les mises à jour passent par lui.
- **Aperçus par défaut** : 60 images/s, qualité 1/4, même rafraîchissement quand Multi OBS est en arrière-plan.
- **Nouvelles instances sur NVIDIA NVENC** aussi en mode de sortie avancé (QP constant pour l'enregistrement) :
  plus d'encodeur AMD de la puce graphique intégrée proposé par défaut.
- Barre de nommage : « output » montre le nom du prochain fichier.

> Depuis la 1.0.0 : « Mettre à jour » ouvre la page de la version. Ferme Multi OBS, télécharge
> `Multi-OBS-Setup.exe` et lance-le.

## 1.0.0

Première version.

- **Instances OBS indépendantes** : chaque instance est un vrai OBS portable avec ses propres scènes,
  profils, réglages et plugins. Plus de plantage quand on modifie l'une d'elles.
- **Une caméra virtuelle par instance** (« OBS Virtual Camera 1, 2, 3… »), sans droits administrateur.
- **Pilotage global** : tout allumer / éteindre, tout enregistrer, tout mettre en pause, raccourcis
  clavier globaux, case « Synchro » pour garder une instance à part.
- **Aperçu en direct sans compression** de chaque instance, avec vumètres audio, images perdues,
  CPU et alertes (pas de son, disque presque plein).
- **Aperçu économe** : jamais plus de pixels que l'écran n'en affiche, pause automatique (fenêtre
  réduite, carte hors écran, session verrouillée, écran éteint), ralenti tout seul si OBS perd
  des images. Par défaut 60 i/s en 1/4, option pour ralentir en arrière-plan.
- **Nommage automatique des fichiers** : `Nom-type-Vidéo-date_heure`, type Cam / Écran / B-roll par instance.
- **MKV converti en MP4** automatiquement à la fin de l'enregistrement (option : MKV à la corbeille).
- **Préconfigs** : enregistre et rouvre un ensemble complet d'instances.
- **Barre des tâches** : chaque instance s'appelle « OBS Blue — Caméra » avec le logo OBS à sa couleur.
- **Espace disque** et dossier d'enregistrement visibles sur chaque carte.
- **Installateur unique** (`Multi-OBS-Setup.exe`, sans droits admin) et **mises à jour** depuis GitHub,
  avec le changelog. Les nouvelles instances utilisent NVIDIA NVENC quand la carte est présente.
