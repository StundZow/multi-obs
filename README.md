# Multi OBS

Plusieurs OBS Studio indépendants, pilotés depuis une seule fenêtre.

Chaque **instance** est un vrai OBS (même version que ton OBS habituel) avec ses propres scènes,
profils, réglages et plugins, sa couleur (thème Yami teinté) et sa propre caméra virtuelle.
Les instances ne partagent aucun fichier de config : modifier l'une ne fait plus planter les autres.

## Installer

1. Télécharge **`Multi-OBS-Setup.exe`** depuis la page [Releases](https://github.com/StundZow/multi-obs/releases).
2. Lance-le : il installe Multi OBS dans `%LOCALAPPDATA%\Programs\Multi OBS` (modifiable), sans droits
   administrateur, avec les raccourcis menu Démarrer / bureau. S'il existe une version plus récente sur
   GitHub, il la télécharge d'abord.
3. Pour désinstaller : Paramètres Windows → Applications → Multi OBS.

> Tant que le dépôt est **privé**, la recherche de mises à jour a besoin d'être authentifiée :
> installe [GitHub CLI](https://cli.github.com/) et connecte-toi avec `gh auth login`, ou définis la
> variable d'environnement `MULTIOBS_GITHUB_TOKEN`. Une fois le dépôt public, rien n'est nécessaire.

**Mises à jour** : au démarrage, Multi OBS vérifie s'il existe une nouvelle version et affiche son
changelog. « Mettre à jour » télécharge le nouvel installateur, qui remplace Multi OBS et le relance.
Les instances OBS continuent de tourner pendant la mise à jour.

Au premier lancement d'une instance, Multi OBS copie ton installation d'OBS dans `data/runtime`
(environ 450 Mo, une seule fois). Les instances pointent vers cette copie par liens physiques et ne
prennent presque pas de place en plus.

## La fenêtre principale

| Zone | Rôle |
|---|---|
| **Tout allumer / Tout éteindre** | Démarre ou arrête l'OBS de toutes les instances |
| **Tout enregistrer / Tout en pause** | Agit sur les instances cochées « Synchro » |
| **Nom / Vidéo** | Nom des fichiers de toutes les instances : `Nom-type-Vidéo-date_heure` |
| **Préconfig** | Enregistre ou rouvre un ensemble complet d'instances (scènes, réglages…) |

Sur chaque carte d'instance :

| Élément | Rôle |
|---|---|
| **Allumer / Éteindre** | Démarre ou arrête l'OBS de l'instance (il tourne réduit, tu le pilotes d'ici) |
| **Voir OBS** | Ouvre la fenêtre OBS de l'instance, pour régler scènes et sources |
| **Rec / Pause** | Enregistrement de cette instance seulement |
| **VCam N** | Allume / éteint sa caméra virtuelle « OBS Virtual Camera N » |
| **Cam / Écran / B-roll / Live** | Type de l'instance, utilisé dans le nom des fichiers |
| **Synchro** | Cochée : l'instance suit « Tout enregistrer », « Tout en pause » et les raccourcis |
| Aperçu, vumètres | Image en direct, niveaux audio (clic sur l'icône = couper), images perdues, CPU |
| Bas de carte | Espace libre du disque (barre rouge sous 200 Go), fichier ou dossier d'enregistrement |

**Raccourcis globaux** (désactivés par défaut, à activer dans ⚙ ; ils marchent même si Multi OBS n'est
pas au premier plan) : `Ctrl+Alt+R` pour tout enregistrer ou arrêter, `Ctrl+Alt+P` pour tout mettre en
pause ou reprendre. Modifiables dans ⚙.

**Barre des tâches** : chaque instance s'appelle « OBS Blue — Caméra », « OBS Red — Écran »…
avec le logo OBS à sa couleur.

## Aperçu : qualité et ressources

L'aperçu est **sans compression** (par défaut 60 i/s, en 1/4). Pour qu'il coûte le moins possible :

- jamais plus de pixels que l'écran n'en affiche (le réglage 1/1, 1/2, 1/4 est un maximum) ;
- jamais plus d'images par seconde que la scène OBS n'en produit ;
- **en pause** quand il ne sert à rien : fenêtre réduite, carte hors de l'écran, aperçu masqué
  (menu ⋮), session verrouillée, écran éteint ;
- option : **ralentir** quand Multi OBS est en arrière-plan (désactivée par défaut) ;
- image figée (écran immobile) : ni décodage ni affichage, vérifiée 2 fois par seconde ;
- si OBS perd des images, l'aperçu se ralentit tout seul pour protéger l'enregistrement ;
- décodage dans un thread à part, de priorité basse.

## Caméras virtuelles

Chaque instance a sa caméra « **OBS Virtual Camera N** » (1, 2, 3…), en plus de « OBS Virtual Camera »
de ton OBS habituel. Elles s'installent automatiquement, sans droits administrateur.

- **Discord, Zoom, navigateur…** : choisis « OBS Virtual Camera 2 », par exemple. Redémarre Discord la
  première fois.
- **Partager la webcam entre instances** : l'instance qui capture la webcam allume sa caméra virtuelle,
  les autres ajoutent une source « Périphérique de capture vidéo » sur « OBS Virtual Camera N ».
  Une instance ne voit pas sa propre caméra virtuelle, ce qui évite les boucles.

## Enregistrements

- **Pause** : les nouvelles instances enregistrent en **MKV**. Le format « MP4 hybride » d'OBS ne gère
  pas la pause, et Multi OBS le signale si c'est le cas.
- **Conversion MP4** : à la fin du rec, OBS convertit le MKV en MP4 (sans perte, quelques secondes).
  Option : mettre le MKV à la corbeille une fois le MP4 vérifié.
- **Nom des fichiers** : modèle réglable dans ⚙, par défaut `{user}-{type}-{video}-{date}_{time}`.
  Si deux instances ont le même type, le nom de l'instance est ajouté.
- **Sécurités** : dossier d'enregistrement introuvable (disque débranché…) → le rec est refusé avec un
  message clair. Si OBS attend une réponse dans sa fenêtre réduite, la carte le signale.

## Mettre à jour OBS

Mets à jour ton OBS habituel normalement, puis ⚙ → « Mettre à jour les instances ».
Multi OBS le propose aussi au lancement. Les scènes et réglages des instances sont conservés.

## Où sont les fichiers

```
<dossier d'installation>/
  Multi OBS.exe
  data/
    runtime/      copie d'OBS
    instances/    une installation OBS portable par instance (config dans instances/instN/config)
    vcam/         modules des caméras virtuelles
    icons/        logos OBS colorés (barre des tâches)
    presets/      préconfigs
    corbeille/    config des instances supprimées (récupérable)
    multiobs.json réglages de Multi OBS
```

## Développement

- Lancer depuis les sources : `python "Multi OBS.pyw"` (Python 3.12+, `pip install PySide6 psutil`).
- Construire : `python build.py` → `dist/Multi-OBS.exe` (l'appli) puis `dist/Multi-OBS-Setup.exe`
  (l'installateur, qui la contient) — `pip install pyinstaller pillow`.
- Publier une version : ajoute une section `## X.Y.Z` dans `CHANGELOG.md`, puis
  `python release.py X.Y.Z`. Ça construit, crée le tag et la release GitHub (seulement l'installateur)
  avec ces notes.
  Les applis installées la proposent au démarrage suivant.

Les icônes de l'interface proviennent d'OBS Studio (GPL-2.0).
