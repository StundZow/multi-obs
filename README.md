<div align="center">

<img src="icon.png" width="96" alt="Icône Multi OBS">

# Multi OBS

Plusieurs **OBS Studio** indépendants, pilotés depuis une seule fenêtre : ta caméra, ton écran et ton live enregistrés séparément, sans que les OBS se marchent dessus.

[**⬇ Télécharger pour Windows**](https://github.com/StundZow/multi-obs/releases/latest/download/Multi-OBS-Setup.exe) · [Releases](https://github.com/StundZow/multi-obs/releases)

<img src="screenshots/01_main.png" width="760" alt="Fenêtre principale de Multi OBS">

<sub>Les aperçus de ces captures sont des images factices.</sub>

</div>

## Ce que ça fait

Pour enregistrer ta caméra et ton écran dans des fichiers séparés — et parfois faire un live en même temps — il faut plusieurs OBS. Multi OBS lance autant d'**instances** que tu veux : chacune est un vrai OBS, avec ses scènes, ses réglages, sa couleur et sa caméra virtuelle, et tu les pilotes toutes depuis une seule fenêtre — aperçu en direct, son, enregistrement, pause.

Les fenêtres OBS restent réduites : tu ne les ouvres (**Voir OBS**) que pour régler tes scènes.

## Pourquoi pas juste ouvrir deux OBS ?

Parce que deux OBS lancés normalement partagent le même dossier de configuration : quand l'un enregistre un réglage, l'autre plante. Et Streamlabs, souvent utilisé comme « deuxième OBS », ne sait pas mettre un enregistrement en pause. Ici, chaque instance a sa propre installation portable : elles ne peuvent pas se gêner.

## Fonctionnalités

- 🧩 **Instances indépendantes** — scènes, profils, plugins et réglages séparés ; aucune ne peut faire planter les autres
- 🔗 **Pilotage global** — tout allumer, tout enregistrer, tout mettre en pause d'un clic ; une instance déliée (**Link**) reste à part, pratique pour le live
- 👀 **Aperçu en direct sans compression**, vumètres audio, images perdues, CPU, et alertes (pas de son, disque presque plein, OBS qui attend une réponse)
- 🎥 **Une caméra virtuelle par instance** — « OBS Virtual Camera 1, 2, 3… » pour Discord, Zoom ou une autre instance, sans droits administrateur
- 🏷️ **Nommage automatique** — `Nom-type-Vidéo-date_heure`, avec tes propres types (Cam, Écran et Live par défaut)
- 🎞️ **MKV → MP4 automatique** à la fin du rec, et option pour mettre le MKV à la corbeille une fois le MP4 vérifié
- 💾 **Espace disque** et fichier en cours affichés sur chaque instance, dossier d'enregistrement en un clic
- 🎨 **Une couleur par instance** — thème OBS teinté, logo coloré dans la barre des tâches, image de caméra virtuelle assortie
- 📦 **Préconfigs** — enregistre et rouvre un ensemble complet d'instances
- 🔄 **Mise à jour automatique** intégrée, avec le changelog

<div align="center">
<img src="screenshots/02_settings.png" width="420" alt="Paramètres : nom des fichiers et types d'enregistrement">
&nbsp;&nbsp;
<img src="screenshots/03_new_instance.png" width="420" alt="Nouvelle instance">
</div>

## Prise en main

1. [Télécharge `Multi-OBS-Setup.exe`](https://github.com/StundZow/multi-obs/releases/latest/download/Multi-OBS-Setup.exe) et lance-le — pas besoin d'être administrateur. [OBS Studio](https://obsproject.com/) doit être installé.
2. Trois cases à cocher (menu Démarrer, bureau, lancer à la fin) et un dossier d'installation modifiable.
3. **Nouvelle instance** : un nom, une couleur, un type. « Partir de mes scènes et réglages OBS actuels » copie ta config OBS — ton OBS habituel n'est pas modifié.
4. **Voir OBS** pour régler les scènes de l'instance, puis pilote tout depuis Multi OBS : **Rec**, **Pause**, **VCam**, et les boutons du haut pour toutes les instances liées.
5. Remplis **Nom** et **Vidéo** en haut : chaque fichier s'appellera par exemple `Stund-cam-Tuto-2026-10-20_17-49-50.mp4`.

## Caméras virtuelles

Chaque instance a sa propre caméra virtuelle, à côté de « OBS Virtual Camera » de ton OBS habituel. Pour partager ta webcam entre plusieurs instances, l'instance qui la capture allume sa **VCam**, et les autres ajoutent une source « Périphérique de capture vidéo » sur « OBS Virtual Camera N ». Une instance ne voit pas sa propre caméra virtuelle, ce qui évite les boucles. Si une caméra disparaît de Windows, Multi OBS la remet tout seul.

Quand une caméra virtuelle est éteinte, son image d'attente prend la couleur de son instance :

<div align="center">
<img src="screenshots/06_vcam.png" width="760" alt="Images d'attente des caméras virtuelles, une par couleur">
</div>

## Barre des tâches

Chaque instance porte un nom clair et le logo OBS à sa couleur, pour s'y retrouver d'un coup d'œil :

<div align="center">
<img src="screenshots/07_taskbar.png" width="760" alt="Barre des tâches avec trois instances">
</div>

## Aperçu économe

L'aperçu est **sans compression** (par défaut 60 images/s en 1/4) et coûte le moins possible :

- jamais plus de pixels que l'écran n'en affiche, ni plus d'images que la scène OBS n'en produit ;
- **en pause** quand il ne sert à rien : fenêtre réduite, carte hors de l'écran, aperçu masqué, session verrouillée, écran éteint ;
- image figée : ni décodage ni affichage ;
- si OBS perd des images, l'aperçu ralentit tout seul pour protéger l'enregistrement ;
- décodage dans un thread à part, de priorité basse.

Mesuré avec trois instances et les réglages par défaut : 2 à 4 % du processeur pour les trois OBS, autant pour Multi OBS, sans image perdue à l'enregistrement.

<div align="center">
<img src="screenshots/05_update.png" width="420" alt="Mise à jour proposée avec le changelog">
&nbsp;&nbsp;
<img src="screenshots/04_settings_preview.png" width="420" alt="Paramètres de l'aperçu">
</div>

## Comment ça marche

- **Une installation OBS portable par instance.** Multi OBS copie ton OBS une fois (`data/runtime`), et chaque instance y pointe par liens physiques : trois instances ne prennent presque pas plus de place qu'une. Chacune a son propre dossier `config/`.
- **Pilotage par obs-websocket**, intégré à OBS : une connexion pour les commandes et l'état, une seconde en binaire (MessagePack) réservée à l'aperçu.
- **Caméras virtuelles** : le module de caméra virtuelle d'OBS est dupliqué et modifié pour chaque instance (identifiant et mémoire partagée propres), puis enregistré pour l'utilisateur courant.
- **Installateur unique** : `Multi-OBS-Setup.exe` contient l'appli. Au lancement, il vérifie s'il existe une version plus récente sur GitHub. Les mises à jour de l'appli téléchargent ce même installateur, qui remplace Multi OBS et le relance — les instances OBS continuent de tourner pendant ce temps.
- **Testé** par une batterie de 59 vérifications : enregistrements simultanés avec pauses (durées, images, son), boutons, raccourcis, aperçus, économies, plantages, redémarrage.

Les données sont dans le dossier d'installation :

```
Multi OBS.exe
data/
  runtime/      copie d'OBS
  instances/    une installation OBS portable par instance
  vcam/         modules des caméras virtuelles
  presets/      préconfigs
  multiobs.json réglages
```

Pour mettre à jour OBS : mets à jour ton OBS habituel, puis ⚙ → Général → « Mettre à jour les instances ».

> Tant que le dépôt est **privé**, la recherche de mises à jour passe par [GitHub CLI](https://cli.github.com/) connecté (`gh auth login`) ou la variable `MULTIOBS_GITHUB_TOKEN`.

## Lancer depuis les sources

```bash
pip install PySide6 psutil
python "Multi OBS.pyw"
```

## Publier une nouvelle version (pour les mainteneurs)

Ajoute une section `## X.Y.Z` dans `CHANGELOG.md`, puis :

```bash
python release.py X.Y.Z
```

Le script reconstruit l'appli et l'installateur (`pip install pyinstaller pillow`), tague la version et publie la release GitHub — avec seulement l'installateur et les notes du changelog. Nécessite [GitHub CLI](https://cli.github.com/) authentifié.

---

Les icônes de l'interface et le logo OBS proviennent d'[OBS Studio](https://github.com/obsproject/obs-studio) (GPL-2.0).
