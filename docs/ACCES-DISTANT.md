# Accéder aux vidéos depuis chez soi

Par défaut, Spash Club n'est joignable que depuis le réseau du club (Wi-Fi).
Pour que les joueurs récupèrent leurs vidéos en 4G ou depuis chez eux, il faut rendre
le PC du club accessible depuis internet.

## Méthode conseillée : Cloudflare Tunnel (gratuit)

Avantages : pas de port à ouvrir sur la box, connexion chiffrée (https), adresse fixe.
Il faut un **nom de domaine** (≈ 10 € par an, par exemple `monclub.fr`) géré par Cloudflare
(compte gratuit).

1. Créer un compte sur <https://dash.cloudflare.com> et y ajouter le nom de domaine du club.
2. Dans **Zero Trust → Networks → Tunnels**, créer un tunnel « spash-club ».
3. Choisir **Windows** : Cloudflare affiche une commande à copier dans une invite de
   commandes **administrateur** sur le PC du club (elle installe le service `cloudflared`,
   qui redémarre tout seul avec le PC).
4. Dans l'onglet **Public Hostname** du tunnel, ajouter :
   - Sous-domaine : `video` ; Domaine : `monclub.fr`
   - Service : `HTTP` → `localhost:8000`
5. Dans `config.toml` :
   ```toml
   url_publique = "https://video.monclub.fr"
   ```
   puis relancer Spash Club. Les QR codes pointent maintenant vers cette adresse,
   qui marche au club comme à la maison.

### Pour un essai rapide sans nom de domaine

Installer `cloudflared` (`winget install Cloudflare.cloudflared`), puis :

```
cloudflared tunnel --url http://localhost:8000
```

Une adresse du type `https://xxxx.trycloudflare.com` s'affiche. Elle change à chaque
lancement : pratique pour tester, pas pour les QR codes imprimés.

## Autre méthode : ouvrir un port sur la box

Possible (redirection du port 8000 vers le PC + adresse IP fixe ou DynDNS), mais
déconseillé : pas de https sans configuration supplémentaire, et le PC est directement
exposé sur internet.

## Sécurité

- **Changez le mot de passe gérant** (`mot_de_passe_admin`) avant d'ouvrir l'accès.
- Chaque match a un lien secret (impossible à deviner) : seuls ceux qui ont le lien voient la vidéo.
- Le QR code du terrain contient une clé : si quelqu'un s'amuse avec le lien du terrain
  depuis chez lui, cliquez sur **Changer le QR code** dans la page gérant et réimprimez-le.

## Débit internet

Quand un joueur regarde sa vidéo depuis chez lui, elle est envoyée par la connexion
du club. Comptez 4 à 8 Mbit/s en envoi par personne qui regarde en même temps.
Si la connexion du club est faible, la vidéo peut mettre du temps à charger. Le futur
serveur (ou un hébergement des vidéos en ligne) réglera ce point.
