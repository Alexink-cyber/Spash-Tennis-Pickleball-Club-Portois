# Trouver l'adresse RTSP de sa caméra

Spash Club lit la caméra par son flux **RTSP**. L'adresse ressemble à :

```
rtsp://UTILISATEUR:MOTDEPASSE@ADRESSE_IP:554/CHEMIN
```

## 1. Trouver l'adresse IP de la caméra

- dans l'application ou le logiciel fourni avec la caméra ;
- ou dans la page d'administration de la box internet (liste des appareils connectés) ;
- ou avec l'outil gratuit **ONVIF Device Manager** (Windows) : il trouve les caméras du réseau
  et affiche directement leur adresse RTSP (onglet « Live video »).

Conseil : donnez une **adresse IP fixe** à la caméra (réglage dans la box ou dans la caméra),
sinon elle peut changer après une coupure.

## 2. Chemins RTSP courants

| Marque | Adresse à essayer |
|---|---|
| Hikvision / HiLook | `rtsp://user:mdp@IP:554/Streaming/Channels/101` |
| Dahua / Amcrest / Imou | `rtsp://user:mdp@IP:554/cam/realmonitor?channel=1&subtype=0` |
| Reolink | `rtsp://user:mdp@IP:554/h264Preview_01_main` |
| TP-Link Tapo / VIGI | `rtsp://user:mdp@IP:554/stream1` |
| Uniview | `rtsp://user:mdp@IP:554/unicast/c1/s0/live` |
| Axis | `rtsp://user:mdp@IP:554/axis-media/media.amp` |
| Foscam | `rtsp://user:mdp@IP:554/videoMain` |
| Ubiquiti UniFi Protect | activer RTSP dans Protect, qui donne l'adresse complète |
| Annke | `rtsp://user:mdp@IP:554/H264/ch1/main/av_stream` |

Si le mot de passe contient des caractères spéciaux (`@`, `:`, `/`, `#`…), remplacez-les :
`@` → `%40`, `:` → `%3A`, `/` → `%2F`, `#` → `%23`.

Pour tester l'adresse avant de la mettre dans `config.toml`, ouvrez-la dans **VLC**
(Média → Ouvrir un flux réseau). Si VLC affiche l'image, Spash Club y arrivera aussi.
Ensuite, sur la page gérant, le bouton **Tester la caméra** affiche une image.

## 3. Réglages conseillés dans la caméra

| Réglage | Valeur conseillée | Pourquoi |
|---|---|---|
| Codec vidéo | **H.264** (pas H.265 / H.265+) | lisible sur tous les téléphones et navigateurs |
| Résolution | 1920×1080 | bon compromis qualité / place disque |
| Images par seconde | 25 | suffisant pour le tennis |
| Intervalle d'images clés (I-frame, GOP) | **25 à 50** (1 à 2 s) | temps forts découpés plus précisément |
| Débit | 4 000 à 8 000 kbit/s | ≈ 2 à 4 Go par heure |
| Fonctions « Smart codec », « H.264+ » | désactivées | évite des vidéos illisibles |

Si la caméra ne peut sortir que du H.265, mettez `reencoder = true` pour ce terrain dans
`config.toml` : le PC convertit la vidéo en H.264 (cela demande plus de processeur).

## 4. Caméra qui n'est pas en RTSP

Toute source que ffmpeg sait lire fonctionne (flux HTTP/MJPEG, webcam USB…). Exemple pour
une webcam USB sous Windows :

```toml
[[terrains]]
id = "1"
nom = "Terrain 1"
camera_url = "video=Nom de la webcam"
arguments_entree = ["-f", "dshow"]
reencoder = true
```
