# Spash Club – vidéo et score des terrains de tennis

Version 1 : une caméra IP par terrain, tout se pilote depuis le téléphone des joueurs,
les vidéos restent sur l'ordinateur du club.

## Ce que ça fait

**Pour les joueurs** (sur leur téléphone, en scannant le QR code du terrain, rien à installer) :

- démarrer / arrêter l'enregistrement du match ;
- compter les points : jeux, sets, tie-break, super tie-break, point décisif, qui sert ;
  bouton « Annuler » en cas d'erreur ;
- **⚡ Temps fort** : garde les ~25 secondes précédentes en clip ;
- **↺ Revoir** : revoir tout de suite le dernier point ;
- à la fin : un lien et un QR code pour récupérer **depuis chez eux** la vidéo complète
  (le score s'affiche par-dessus pendant la lecture), les temps forts, et les télécharger
  ou les partager ;
- outil de dessin sur la vidéo pour le coaching.

**Pour le club** (page gérant `/admin`, protégée par mot de passe) :

- QR code de chaque terrain à imprimer ;
- tester la caméra (aperçu d'image) ;
- lancer / arrêter un **direct YouTube** avec le score et le logo du club incrustés ;
- liste des matchs, suppression, espace disque restant ;
- suppression automatique des vieux matchs (30 jours par défaut).

## Installation sur l'ordinateur du club (Windows)

1. Installer **Python 3.11 ou plus récent** depuis <https://www.python.org/downloads/>
   en cochant **« Add python.exe to PATH »**.
2. *(Recommandé)* Installer ffmpeg : ouvrir « Invite de commandes » et taper
   `winget install Gyan.FFmpeg`. Sans cela, une version de secours est installée
   automatiquement.
3. Télécharger ce dossier (bouton vert **Code → Download ZIP** sur GitHub) et le dézipper,
   par exemple dans `C:\SpashClub`.
4. Double-cliquer sur **`demarrer.bat`**. La première fois, il installe ce qu'il faut
   et ouvre `config.toml` dans le Bloc-notes :
   - `camera_url` : l'adresse de la caméra → voir [docs/CAMERAS.md](docs/CAMERAS.md) ;
   - `mot_de_passe_admin` : à changer ;
   - `nom` du club.
5. Relancer `demarrer.bat`. La fenêtre affiche l'adresse de la page gérant, par exemple
   `http://192.168.1.20:8000/admin`.
6. Sur la page gérant : **Tester la caméra**, puis **imprimer le QR code** du terrain
   et l'afficher au bord du terrain.

Laisser la fenêtre ouverte : fermer la fenêtre arrête le service. Pour un lancement
automatique au démarrage du PC, placer un raccourci vers `demarrer.bat` dans le dossier
`shell:startup` (touche Windows + R, taper `shell:startup`).

### Points importants pour le PC

- Désactiver la **mise en veille** (Paramètres → Système → Alimentation).
- Autoriser Python dans le **pare-feu Windows** quand Windows le demande
  (réseaux privés), sinon les téléphones ne pourront pas se connecter.
- Brancher le PC et la caméra en **câble réseau**.

## Accès depuis chez soi (4G, maison)

Les vidéos sont sur le PC du club : il faut le rendre joignable depuis internet.
La méthode conseillée (gratuite, sans ouvrir de port sur la box) est expliquée dans
[docs/ACCES-DISTANT.md](docs/ACCES-DISTANT.md). Une fois en place, renseigner
`url_publique` dans `config.toml` : les QR codes utiliseront cette adresse.

## Direct YouTube

1. YouTube Studio → **Créer → Passer au direct → Flux** → copier la **clé de flux**.
   (La première activation du direct sur une chaîne peut prendre 24 h.)
2. La coller dans `cle` (section `[direct]` de `config.toml`), relancer.
3. Page gérant → **Lancer le direct** sur le terrain voulu.

Il faut environ **5 Mbit/s en envoi** (upload) pour du 720p. Testez votre connexion
sur un site de test de débit avant. Avec une carte NVIDIA, mettez `encodeur = "h264_nvenc"`
pour soulager le processeur. Pensez à prévenir les joueurs avant de les diffuser.

## Stockage

Environ **3 à 4 Go par heure** de match en 1080p. Les vidéos sont dans le dossier `data/`
(réglable dans `config.toml`). Pour le futur serveur avec des disques dédiés, il suffira
de changer `dossier` dans la section `[stockage]`.

## Pour les développeurs

```bash
python -m venv .venv && . .venv/bin/activate      # Windows : .venv\Scripts\activate
pip install -r requirements-dev.txt
python -m pytest                                  # tests (une fausse caméra est simulée)
python -m spash --config config.toml              # lancer le serveur
```

Organisation du code (`spash/`) :

| Fichier | Rôle |
|---|---|
| `tennis.py` | règles de comptage du tennis (recalcul à partir de la liste des points) |
| `recorder.py` | enregistrement de la caméra en segments de 2 s, découpe des clips, assemblage final |
| `live.py`, `overlay.py` | direct RTMP avec bandeau de score dessiné en Python |
| `club.py` | logique : matchs en cours, clips, direct, ménage, reprise après coupure |
| `app.py` | serveur web (FastAPI) et API |
| `static/` | pages : terrain (`court.html`), match (`match.html`), gérant (`admin.html`) |

Choix techniques :

- **Compatibilité caméras** : tout passe par le flux **RTSP**, que presque toutes les caméras IP
  proposent (Hikvision, Dahua, Reolink, TP-Link, Axis, Uniview…). La vidéo est copiée sans
  réencodage : le PC travaille très peu.
- **Pas de base de score figée** : on garde la liste des points ; annuler = retirer le dernier.
  Chaque point est horodaté, ce qui permet d'afficher le bon score à chaque instant du replay.
- **Coupure de courant** : au redémarrage, les matchs interrompus sont assemblés automatiquement.

### Pistes pour la suite

- reconnexion automatique si la caméra décroche en plein match ;
- export de la vidéo avec le score incrusté dans le fichier ;
- écrans au bar du club (diaporama des derniers temps forts) ;
- détection automatique des échanges / temps forts, puis le pickleball.
