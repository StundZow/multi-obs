# Changelog

Chaque version publiée avec `python release.py X.Y.Z` reprend la section correspondante :
c'est ce texte que Multi OBS affiche quand il propose la mise à jour.

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
