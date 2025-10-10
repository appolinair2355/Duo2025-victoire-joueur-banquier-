# ==================== PROJET 1: Bot de Stockage de Résultats ====================
import os
import asyncio
import json
import logging
import sys
import zipfile
import shutil
from datetime import datetime, timedelta, timezone
from telethon import TelegramClient, events
from telethon.events import ChatAction
from dotenv import load_dotenv
from game_results_manager import GameResultsManager
from yaml_manager import YAMLDataManager
from aiohttp import web
from pathlib import Path

# ==================== PROJET 2: Système de Prédiction ====================
from predictor import CardPredictor
from excel_importer import ExcelPredictionManager

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('bot.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

# Charger les variables d'environnement
load_dotenv()

# --- CONFIGURATION ---
try:
    API_ID = int(os.getenv('API_ID') or '0')
    API_HASH = os.getenv('API_HASH') or ''
    BOT_TOKEN = os.getenv('BOT_TOKEN') or ''
    ADMIN_ID = int(os.getenv('ADMIN_ID') or '0')
    PORT = int(os.getenv('PORT') or '10000')

    # Validation des variables requises
    if not API_ID or API_ID == 0:
        raise ValueError("API_ID manquant ou invalide")
    if not API_HASH:
        raise ValueError("API_HASH manquant")
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN manquant")

    logger.info(f"✅ Configuration chargée: API_ID={API_ID}, ADMIN_ID={ADMIN_ID}, PORT={PORT}")
except Exception as e:
    logger.error(f"❌ Erreur configuration: {e}")
    logger.error("Vérifiez vos variables d'environnement dans le fichier .env")
    exit(1)

# Fichier de configuration
CONFIG_FILE = 'bot_config.json'

# Variables globales
detected_stat_channel = None
confirmation_pending = {}
transfer_enabled = True

# ==================== GESTIONNAIRES PROJET 1 ====================
yaml_manager = YAMLDataManager()
results_manager = GameResultsManager()

# ==================== GESTIONNAIRES PROJET 2 ====================
predictor = CardPredictor()
excel_manager = ExcelPredictionManager()
detected_display_channel = None
prediction_interval = 1

# Client Telegram
import time
session_name = f'bot_session_{int(time.time())}'
client = TelegramClient(session_name, API_ID, API_HASH)


def load_config():
    """Charge la configuration depuis le fichier JSON"""
    global detected_stat_channel
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                config = json.load(f)
                detected_stat_channel = config.get('stat_channel')
                logger.info(f"✅ Configuration chargée: Canal={detected_stat_channel}")
        else:
            logger.info("ℹ️ Aucune configuration trouvée")
    except Exception as e:
        logger.warning(f"⚠️ Erreur chargement configuration: {e}")


def save_config():
    """Sauvegarde la configuration dans le fichier JSON"""
    try:
        config = {
            'stat_channel': detected_stat_channel
        }
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2)

        if yaml_manager:
            yaml_manager.set_config('stat_channel', detected_stat_channel)

        logger.info(f"💾 Configuration sauvegardée: Canal={detected_stat_channel}")
    except Exception as e:
        logger.error(f"❌ Erreur sauvegarde configuration: {e}")


async def start_bot():
    """Démarre le bot"""
    try:
        logger.info("🚀 DÉMARRAGE DU BOT...")
        load_config()
        await client.start(bot_token=BOT_TOKEN)
        logger.info("✅ Bot Telegram connecté")

        me = await client.get_me()
        username = getattr(me, 'username', 'Unknown') or f"ID:{getattr(me, 'id', 'Unknown')}"
        logger.info(f"✅ Bot opérationnel: @{username}")

        if detected_stat_channel:
            logger.info(f"📊 Surveillance du canal: {detected_stat_channel}")
        else:
            logger.info("⚠️ Aucun canal configuré. Ajoutez le bot à un canal pour commencer.")

    except Exception as e:
        logger.error(f"❌ Erreur démarrage: {e}")
        return False

    return True


# --- GESTION DES INVITATIONS ---
@client.on(events.ChatAction())
async def handler_join(event):
    """Gère l'ajout du bot à un canal"""
    global confirmation_pending

    try:
        if event.user_joined or event.user_added:
            me = await client.get_me()
            me_id = getattr(me, 'id', None)

            if event.user_id == me_id:
                channel_id = event.chat_id

                if str(channel_id).startswith('-207') and len(str(channel_id)) == 14:
                    channel_id = int('-100' + str(channel_id)[4:])

                if channel_id in confirmation_pending:
                    return

                confirmation_pending[channel_id] = 'waiting_confirmation'

                try:
                    chat = await client.get_entity(channel_id)
                    chat_title = getattr(chat, 'title', f'Canal {channel_id}')
                except:
                    chat_title = f'Canal {channel_id}'

                invitation_msg = f"""🔔 **Nouveau canal détecté**

📋 **Canal** : {chat_title}
🆔 **ID** : {channel_id}

Pour surveiller ce canal et stocker les résultats:
• `/set_channel {channel_id}`

Le bot stockera automatiquement les parties où le premier groupe de parenthèses contient exactement 3 cartes différentes."""

                try:
                    await client.send_message(ADMIN_ID, invitation_msg)
                    logger.info(f"✉️ Invitation envoyée pour: {chat_title} ({channel_id})")
                except Exception as e:
                    logger.error(f"❌ Erreur envoi invitation: {e}")

    except Exception as e:
        logger.error(f"❌ Erreur dans handler_join: {e}")


@client.on(events.NewMessage(pattern=r'/set_channel (-?\d+)'))
async def set_channel(event):
    """Configure le canal à surveiller"""
    global detected_stat_channel, confirmation_pending

    try:
        if event.is_group or event.is_channel:
            return

        if event.sender_id != ADMIN_ID:
            await event.respond("❌ Seul l'administrateur peut configurer les canaux")
            return

        match = event.pattern_match
        channel_id = int(match.group(1))

        if channel_id not in confirmation_pending:
            await event.respond("❌ Ce canal n'est pas en attente de configuration")
            return

        detected_stat_channel = channel_id
        confirmation_pending[channel_id] = 'configured'
        save_config()

        try:
            chat = await client.get_entity(channel_id)
            chat_title = getattr(chat, 'title', f'Canal {channel_id}')
        except:
            chat_title = f'Canal {channel_id}'

        await event.respond(f"""✅ **Canal configuré avec succès**
📋 {chat_title}

Le bot va maintenant:
• Surveiller les messages de ce canal
• Stocker les parties avec 3 cartes dans le premier groupe
• Identifier le gagnant (Joueur ou Banquier)
• Ignorer les matchs nuls et les cas où les deux groupes ont 3 cartes

Utilisez /fichier pour exporter les résultats.""")

        logger.info(f"✅ Canal configuré: {channel_id}")

    except Exception as e:
        logger.error(f"❌ Erreur set_channel: {e}")


transferred_messages = {}


@client.on(events.NewMessage())
async def handle_message(event):
    """Traite les messages entrants"""
    try:
        me = await client.get_me()
        if event.sender_id == me.id:
            return

        if not event.is_group and not event.is_channel:
            if event.sender_id in confirmation_pending:
                pending_action = confirmation_pending.get(event.sender_id)
                if isinstance(pending_action, dict) and pending_action.get('action') == 'reset_database':
                    message_text = event.message.message.strip().upper()
                    if message_text == 'OUI':
                        await event.respond("🔄 **Remise à zéro en cours...**")

                        results_manager._save_yaml([])
                        logger.info("✅ Base de données remise à zéro manuellement")

                        timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
                        new_file_path = f"resultats_{timestamp}.xlsx"
                        empty_file = results_manager.export_to_txt(file_path=new_file_path)

                        if empty_file and os.path.exists(empty_file):
                            await client.send_file(
                                event.sender_id,
                                empty_file,
                                caption="📄 **Nouveau fichier Excel créé**\n\nLe fichier est vide et prêt pour de nouvelles données."
                            )

                        await event.respond("✅ **Remise à zéro effectuée**\n\nLa base de données a été réinitialisée avec succès!")
                        del confirmation_pending[event.sender_id]
                        return
                    else:
                        await event.respond("❌ **Remise à zéro annulée**\n\nVeuillez répondre 'OUI' pour confirmer la remise à zéro.")
                        del confirmation_pending[event.sender_id]
                        return

        if detected_stat_channel and event.chat_id == detected_stat_channel:
            message_text = event.message.message
            logger.info(f"📨 Message du canal: {message_text[:100]}...")

            if transfer_enabled:
                try:
                    transfer_msg = f"📨 **Message du canal:**\n\n{message_text}"
                    sent_msg = await client.send_message(ADMIN_ID, transfer_msg)
                    transferred_messages[event.message.id] = sent_msg.id
                except Exception as e:
                    logger.error(f"❌ Erreur transfert message: {e}")

            success, info = results_manager.process_message(message_text)

            if success:
                logger.info(f"✅ {info}")
                try:
                    stats = results_manager.get_stats()
                    notification = f"""✅ **Partie enregistrée!**

{info}

📊 **Statistiques actuelles:**
• Total: {stats['total']} parties
• Joueur: {stats['joueur_victoires']} ({stats['taux_joueur']:.1f}%)
• Banquier: {stats['banquier_victoires']} ({stats['taux_banquier']:.1f}%)"""
                    await client.send_message(ADMIN_ID, notification)
                except Exception as e:
                    logger.error(f"Erreur notification: {e}")
            else:
                logger.info(f"⚠️ Message ignoré: {info}")

    except Exception as e:
        logger.error(f"❌ Erreur traitement message: {e}")
        import traceback
        logger.error(traceback.format_exc())


@client.on(events.MessageEdited())
async def handle_edited_message(event):
    """Traite les messages édités"""
    try:
        if detected_stat_channel and event.chat_id == detected_stat_channel:
            message_text = event.message.message
            logger.info(f"✏️ Message édité dans le canal: {message_text[:100]}...")

            if transfer_enabled:
                if event.message.id in transferred_messages:
                    admin_msg_id = transferred_messages[event.message.id]
                    try:
                        transfer_msg = f"📨 **Message du canal (✏️ ÉDITÉ):**\n\n{message_text}"
                        await client.edit_message(ADMIN_ID, admin_msg_id, transfer_msg)
                        logger.info(f"✅ Message transféré édité")
                    except Exception as e:
                        logger.error(f"❌ Erreur édition message transféré: {e}")
                else:
                    try:
                        transfer_msg = f"📨 **Message du canal (✏️ ÉDITÉ - nouveau):**\n\n{message_text}"
                        sent_msg = await client.send_message(ADMIN_ID, transfer_msg)
                        transferred_messages[event.message.id] = sent_msg.id
                    except Exception as e:
                        logger.error(f"❌ Erreur transfert message édité: {e}")

            success, info = results_manager.process_message(message_text)

            if success:
                logger.info(f"✅ {info}")
                try:
                    stats = results_manager.get_stats()
                    notification = f"""✅ **Partie enregistrée (message finalisé)!**

{info}

📊 **Statistiques actuelles:**
• Total: {stats['total']} parties
• Joueur: {stats['joueur_victoires']} ({stats['taux_joueur']:.1f}%)
• Banquier: {stats['banquier_victoires']} ({stats['taux_banquier']:.1f}%)"""
                    await client.send_message(ADMIN_ID, notification)
                except Exception as e:
                    logger.error(f"Erreur notification: {e}")
            else:
                if "en cours d'édition" not in info:
                    logger.info(f"⚠️ Message édité ignoré: {info}")

    except Exception as e:
        logger.error(f"❌ Erreur traitement message édité: {e}")
        import traceback
        logger.error(traceback.format_exc())


@client.on(events.NewMessage(pattern='/start'))
async def cmd_start(event):
    """Commande /start"""
    if event.is_group or event.is_channel:
        return

    await event.respond("""👋 **Bot de Stockage de Résultats de Jeux**

Ce bot stocke automatiquement les résultats des parties où le premier groupe de parenthèses contient exactement 3 cartes différentes.

**Commandes disponibles:**
• `/status` - Voir l'état du bot et les statistiques
• `/fichier` - Exporter les résultats en fichier Excel
• `/help` - Aide détaillée

**Configuration:**
1. Ajoutez le bot à votre canal
2. Utilisez `/set_channel` pour configurer
3. Le bot enregistrera automatiquement les résultats

Développé pour stocker les victoires Joueur/Banquier.""")


@client.on(events.NewMessage(pattern='/status'))
async def cmd_status(event):
    """Affiche le statut du bot"""
    if event.is_group or event.is_channel:
        return

    if event.sender_id != ADMIN_ID:
        await event.respond("❌ Commande réservée à l'administrateur")
        return

    try:
        stats = results_manager.get_stats()

        status_msg = f"""📊 **STATUT DU BOT**

**Configuration:**
• Canal surveillé: {f'✅ Configuré (ID: {detected_stat_channel})' if detected_stat_channel else '❌ Non configuré'}
• Transfert des messages: {'🔔 Activé' if transfer_enabled else '🔕 Désactivé'}

**Statistiques:**
• Total de parties: {stats['total']}
• Victoires Joueur: {stats['joueur_victoires']} ({stats['taux_joueur']:.1f}%)
• Victoires Banquier: {stats['banquier_victoires']} ({stats['taux_banquier']:.1f}%)

**Critères de stockage:**
✅ Exactement 3 cartes dans le premier groupe
✅ Gagnant identifiable (Joueur ou Banquier)
❌ Ignore les matchs nuls
❌ Ignore si les deux groupes ont 3 cartes

Utilisez /fichier pour exporter les résultats."""

        await event.respond(status_msg)

    except Exception as e:
        logger.error(f"❌ Erreur status: {e}")
        await event.respond(f"❌ Erreur: {e}")


@client.on(events.NewMessage(pattern='/fichier'))
async def cmd_fichier(event):
    """Exporte les résultats en fichier Excel"""
    if event.is_group or event.is_channel:
        return

    if event.sender_id != ADMIN_ID:
        await event.respond("❌ Commande réservée à l'administrateur")
        return

    try:
        await event.respond("📊 Génération du fichier Excel en cours...")
        file_path = results_manager.export_to_txt()

        if file_path and os.path.exists(file_path):
            await client.send_file(
                event.chat_id,
                file_path,
                caption="📊 **Export des résultats**\n\nFichier Excel généré avec succès!"
            )
            logger.info("✅ Fichier Excel exporté et envoyé")
        else:
            await event.respond("❌ Erreur lors de la génération du fichier Excel")

    except Exception as e:
        logger.error(f"❌ Erreur export fichier: {e}")
        await event.respond(f"❌ Erreur: {e}")


@client.on(events.NewMessage(pattern='/deploy'))
async def cmd_deploy(event):
    """Crée un package de déploiement pour Render.com"""
    if event.is_group or event.is_channel:
        return

    if event.sender_id != ADMIN_ID:
        await event.respond("❌ Commande réservée à l'administrateur")
        return

    try:
        await event.respond("📦 Préparation du package de déploiement pour Render.com...")

        benin_tz = timezone(timedelta(hours=1))
        now_benin = datetime.now(benin_tz)
        timestamp = now_benin.strftime('%Y-%m-%d_%H-%M-%S')
        
        deploy_dir = Path(f"deploy_render_{timestamp}")
        deploy_dir.mkdir(exist_ok=True)

        files_to_copy = [
            'main.py',
            'game_results_manager.py',
            'yaml_manager.py'
        ]

        for file in files_to_copy:
            if os.path.exists(file):
                shutil.copy(file, deploy_dir / file)

        render_yaml = """services:
  - type: web
    name: bot-telegram-bcarte
    env: python
    region: frankfurt
    plan: starter
    buildCommand: pip install -r requirements.txt
    startCommand: python main.py
    envVars:
      - key: PORT
        value: 10000
      - key: API_ID
        sync: false
      - key: API_HASH
        sync: false
      - key: BOT_TOKEN
        sync: false
      - key: ADMIN_ID
        sync: false
"""

        with open(deploy_dir / 'render.yaml', 'w', encoding='utf-8') as f:
            f.write(render_yaml)

        requirements = """telethon==1.35.0
aiohttp==3.9.5
python-dotenv==1.0.1
pyyaml==6.0.1
openpyxl==3.1.2
"""

        with open(deploy_dir / 'requirements.txt', 'w', encoding='utf-8') as f:
            f.write(requirements)
        
        env_example = """# Variables d'environnement pour le bot Telegram
# Ne jamais committer ces valeurs réelles !

API_ID=votre_api_id
API_HASH=votre_api_hash
BOT_TOKEN=votre_bot_token
ADMIN_ID=votre_admin_id
PORT=10000
"""

        with open(deploy_dir / '.env.example', 'w', encoding='utf-8') as f:
            f.write(env_example)

        readme = f"""# Bot Telegram - Package de Déploiement Render.com

📅 **Créé le:** {now_benin.strftime('%d/%m/%Y à %H:%M:%S')} (Heure Bénin UTC+1)
📦 **Version:** {timestamp}

## 🚀 Instructions de déploiement sur Render.com

### Étape 1: Créer un repository GitHub
1. Créez un nouveau repository sur GitHub
2. Uploadez tous les fichiers de ce package

### Étape 2: Déployer sur Render.com
1. Connectez-vous à [render.com](https://render.com)
2. Cliquez sur **"New +"** → **"Web Service"**
3. Connectez votre repository GitHub
4. Render détectera automatiquement `render.yaml`

### Étape 3: Configurer les Variables d'Environnement
Dans la section **Environment** de Render.com, ajoutez:
- **PORT**: 10000 (déjà configuré)
- **API_ID**: Obtenez-le sur https://my.telegram.org
- **API_HASH**: Obtenez-le sur https://my.telegram.org
- **BOT_TOKEN**: Créez un bot avec @BotFather sur Telegram
- **ADMIN_ID**: Obtenez votre ID avec @userinfobot sur Telegram

### Étape 4: Déployer
1. Cliquez sur **"Create Web Service"**
2. Attendez le déploiement (2-3 minutes)
3. Le bot sera en ligne 24/7 !

## ✅ Fonctionnalités principales

- ✅ **Détection automatique**: Reconnaît les parties avec 3 cartes différentes
- ✅ **Export quotidien**: Génère un fichier Excel à 00h59 (UTC+1)
- ✅ **Réinitialisation auto**: Reset automatique à 01h00
- ✅ **Statistiques en temps réel**: Taux de victoire Joueur/Banquier

## 📊 Commandes disponibles

- `/start` - Démarrer le bot et voir les informations
- `/status` - Voir les statistiques actuelles
- `/fichier` - Exporter les résultats en Excel
- `/reset` - Réinitialiser la base de données manuellement
- `/deploy` - Créer un nouveau package de déploiement
- `/help` - Afficher l'aide complète

## 🎯 Critères d'enregistrement

### ✅ Parties enregistrées:
- Premier groupe: **exactement 3 cartes de couleurs différentes**
- Deuxième groupe: **PAS 3 cartes**
- Gagnant identifiable: **Joueur** ou **Banquier**

### ❌ Parties ignorées:
- Match nul
- Les deux groupes ont 3 cartes
- Pas de numéro de jeu identifiable

## ⚙️ Configuration technique

- **Langage**: Python 3.11
- **Timezone**: Africa/Porto-Novo (UTC+1)
- **Port**: 10000 (Render.com)
- **Export automatique**: 00h59 chaque jour
- **Reset automatique**: 01h00 chaque jour

---
*Package généré automatiquement*
*Dernière mise à jour: {now_benin.strftime('%d/%m/%Y %H:%M:%S')}*
"""

        with open(deploy_dir / 'README_DEPLOIEMENT.md', 'w', encoding='utf-8') as f:
            f.write(readme)

        deploy_zip = "Kouamé.zip"
        with zipfile.ZipFile(deploy_zip, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(deploy_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, deploy_dir)
                    zipf.write(file_path, arcname)

        short_caption = f"""📦 **Package Render.com - Kouamé**

📅 {now_benin.strftime('%d/%m/%Y %H:%M:%S')} (Bénin)
📁 Kouamé.zip
✅ Port 10000 configuré
✅ Export à 00h59
✅ Reset à 01h00"""

        await client.send_file(
            ADMIN_ID,
            deploy_zip,
            caption=short_caption
        )

        shutil.rmtree(deploy_dir)
        logger.info(f"✅ Package créé: {deploy_zip}")

    except Exception as e:
        logger.error(f"❌ Erreur création package: {e}")
        await event.respond(f"❌ Erreur: {e}")


@client.on(events.NewMessage(pattern='/stop_transfer'))
async def cmd_stop_transfer(event):
    """Désactive le transfert des messages du canal"""
    global transfer_enabled

    if event.is_group or event.is_channel:
        return

    if event.sender_id != ADMIN_ID:
        await event.respond("❌ Seul l'administrateur peut contrôler le transfert")
        return

    transfer_enabled = False
    await event.respond("🔕 **Transfert des messages désactivé**\n\nLes messages du canal ne seront plus transférés en privé.\n\nUtilisez /start_transfer pour réactiver.")
    logger.info("🔕 Transfert des messages désactivé")


@client.on(events.NewMessage(pattern='/start_transfer'))
async def cmd_start_transfer(event):
    """Active le transfert des messages du canal"""
    global transfer_enabled

    if event.is_group or event.is_channel:
        return

    if event.sender_id != ADMIN_ID:
        await event.respond("❌ Seul l'administrateur peut contrôler le transfert")
        return

    transfer_enabled = True
    await event.respond("🔔 **Transfert des messages activé**\n\nLes messages du canal seront à nouveau transférés en privé.")
    logger.info("🔔 Transfert des messages activé")


@client.on(events.NewMessage(pattern='/reset'))
async def cmd_reset(event):
    """Remet à zéro la base de données manuellement"""
    if event.is_group or event.is_channel:
        return

    if event.sender_id != ADMIN_ID:
        await event.respond("❌ Commande réservée à l'administrateur")
        return

    try:
        await event.respond("⚠️ **Confirmation requise**\n\nÊtes-vous sûr de vouloir remettre à zéro la base de données?\n\nRépondez 'OUI' pour confirmer.")

        confirmation_pending[event.sender_id] = {
            'action': 'reset_database',
            'timestamp': datetime.now()
        }

        logger.info("⚠️ Confirmation de remise à zéro en attente")

    except Exception as e:
        logger.error(f"❌ Erreur commande reset: {e}")
        await event.respond(f"❌ Erreur: {e}")


@client.on(events.NewMessage(pattern='/deploy_duo2'))
async def cmd_deploy_duo2(event):
    """Crée un package 'duo Final.zip' avec Projet 1 + Projet 2 optimisé pour Render.com (Port 10000)"""
    if event.is_group or event.is_channel:
        return

    if event.sender_id != ADMIN_ID:
        await event.respond("❌ Commande réservée à l'administrateur")
        return

    try:
        await event.respond("📦 Création du package 'duo Final' pour Render.com (Port 10000)...")

        benin_tz = timezone(timedelta(hours=1))
        now_benin = datetime.now(benin_tz)
        timestamp = now_benin.strftime('%Y-%m-%d_%H-%M-%S')
        
        package_name = "duo Final.zip"
        
        with zipfile.ZipFile(package_name, 'w', zipfile.ZIP_DEFLATED) as zipf:
            # ========== FICHIERS PROJET 1 + PROJET 2 ==========
            all_files = [
                'main.py',
                'game_results_manager.py',
                'yaml_manager.py',
                'predictor.py',
                'excel_importer.py'
            ]
            
            # Copier tous les fichiers Python
            for file in all_files:
                if os.path.exists(file):
                    zipf.write(file, file)
                    logger.info(f"  ✅ Ajouté: {file}")
                    
            # ========== CONFIGURATION BOT ==========
            config = {
                "stat_channel": detected_stat_channel,
                "display_channel": detected_display_channel,
                "prediction_interval": prediction_interval
            }
            zipf.writestr('bot_config.json', json.dumps(config, indent=2))
            logger.info("  ✅ Ajouté: bot_config.json")
            
            # ========== REQUIREMENTS.TXT ==========
            requirements = """telethon==1.35.0
aiohttp==3.9.5
python-dotenv==1.0.1
pyyaml==6.0.1
openpyxl==3.1.2"""
            zipf.writestr('requirements.txt', requirements)
            logger.info("  ✅ Ajouté: requirements.txt")
            
            # ========== .ENV.EXAMPLE ==========
            env_example = """# Variables d'environnement Render.com
# NE JAMAIS committer les valeurs réelles!

API_ID=votre_api_id
API_HASH=votre_api_hash
BOT_TOKEN=votre_bot_token
ADMIN_ID=votre_admin_id
PORT=10000"""
            zipf.writestr('.env.example', env_example)
            logger.info("  ✅ Ajouté: .env.example")
            
            # ========== RENDER.YAML ==========
            render_yaml = """services:
  - type: web
    name: bot-telegram-duo-final
    env: python
    region: frankfurt
    plan: starter
    buildCommand: pip install -r requirements.txt
    startCommand: python main.py
    envVars:
      - key: PORT
        value: 10000
      - key: API_ID
        sync: false
      - key: API_HASH
        sync: false
      - key: BOT_TOKEN
        sync: false
      - key: ADMIN_ID
        sync: false
"""
            zipf.writestr('render.yaml', render_yaml)
            logger.info("  ✅ Ajouté: render.yaml")
            
            # ========== PROCFILE ==========
            procfile = "web: python main.py"
            zipf.writestr('Procfile', procfile)
            logger.info("  ✅ Ajouté: Procfile")
            
            # ========== RUNTIME.TXT ==========
            runtime = "python-3.11.0"
            zipf.writestr('runtime.txt', runtime)
            logger.info("  ✅ Ajouté: runtime.txt")
            
            # ========== STRUCTURE DATA/ ==========
            zipf.writestr('data/.gitkeep', '# Dossier pour fichiers YAML\n# Créé automatiquement par le bot\n')
            logger.info("  ✅ Ajouté: data/.gitkeep")
            
            # ========== README.MD COMPLET ==========
            readme = f"""# 📦 Package "duo Final" - Bot Telegram Render.com

📅 **Créé le:** {now_benin.strftime('%d/%m/%Y à %H:%M:%S')} (Heure Bénin UTC+1)
📦 **Version:** {timestamp}
🚀 **Optimisé pour:** Render.com (Port 10000)

---

## 🎯 Contenu du Package

### ✅ **Projet 1: Stockage de Résultats**
- 📊 Surveillance de canal source automatique
- 💾 Stockage parties avec 3 cartes différentes
- 📤 Export Excel quotidien à 00h59 (UTC+1)
- 🔄 Reset automatique à 01h00
- 🎯 Détection automatique du gagnant (Joueur/Banquier)
- ❌ Filtrage des numéros consécutifs
- 📥 **Import automatique dans Projet 2 après export**

### ✅ **Projet 2: Système de Prédictions Excel**
- 📥 Import de prédictions Excel (.xlsx)
- 🚀 Lancement automatique basé sur proximité (tolérance 0-4)
- 🔢 **Filtrage automatique des numéros consécutifs**
- ✅ Vérification avec offsets (0, 1, 2)
- 🎨 Format V1 (Joueur) / V2 (Banquier)
- 📊 Statistiques en temps réel

---

## 📋 Fichiers Inclus dans le Package

### **Code Source (Projet 1 + Projet 2):**
- ✅ `main.py` - Fichier principal (projets fusionnés)
- ✅ `game_results_manager.py` - Gestionnaire résultats Projet 1
- ✅ `yaml_manager.py` - Gestionnaire données YAML
- ✅ `predictor.py` - Système de prédictions Projet 2
- ✅ `excel_importer.py` - Import et gestion Excel Projet 2

### **Configuration Render.com:**
- ✅ `render.yaml` - Déploiement automatique
- ✅ `Procfile` - Commande de démarrage
- ✅ `runtime.txt` - Version Python 3.11
- ✅ `requirements.txt` - Dépendances Python
- ✅ `bot_config.json` - Configuration canaux
- ✅ `.env.example` - Template variables d'environnement

### **Structure:**
- ✅ `data/` - Dossier pour fichiers YAML (auto-créé)
- ✅ `README.md` - Ce fichier de documentation

---

## 🚀 Déploiement sur Render.com

### **Étape 1: Créer un Repository GitHub**
1. Allez sur [github.com](https://github.com)
2. Créez un nouveau repository (public ou privé)
3. Uploadez **TOUS** les fichiers du package "duo Final.zip"

### **Étape 2: Connecter à Render.com**
1. Allez sur [render.com](https://render.com)
2. Cliquez sur **"New +"** → **"Web Service"**
3. Connectez votre repository GitHub
4. Render détectera automatiquement `render.yaml`

### **Étape 3: Configurer les Variables d'Environnement**
Dans la section **Environment** de Render.com, ajoutez:

| Variable | Valeur | Où l'obtenir |
|----------|--------|--------------|
| **PORT** | 10000 | Déjà configuré automatiquement |
| **API_ID** | Votre ID | https://my.telegram.org |
| **API_HASH** | Votre Hash | https://my.telegram.org |
| **BOT_TOKEN** | Token du bot | @BotFather sur Telegram |
| **ADMIN_ID** | Votre ID Telegram | @userinfobot sur Telegram |

### **Étape 4: Déployer**
1. Cliquez sur **"Create Web Service"**
2. Attendez le déploiement (2-3 minutes)
3. ✅ Le bot sera en ligne 24/7 sur le port 10000!

---

## 📊 Commandes Disponibles

### **Projet 1 (Stockage de Résultats):**
- `/start` - Démarrer le bot et voir les infos
- `/status` - Voir les statistiques
- `/fichier` - Exporter résultats en Excel
- `/reset` - Reset manuel de la base
- `/set_channel <ID>` - Configurer canal source
- `/stop_transfer` - Désactiver transfert messages
- `/start_transfer` - Réactiver transfert messages

### **Projet 2 (Prédictions Excel):**
- `/set_display <ID>` - Configurer canal affichage
- `/stats_excel` - Statistiques prédictions Excel
- `/clear_excel` - Effacer toutes les prédictions
- **Envoyer fichier Excel (.xlsx)** - Import automatique

### **Autres Commandes:**
- `/deploy` - Créer package Render.com (Projet 1)
- `/deploy_duo2` - Créer package "duo Final" (Projet 1 + 2)
- `/help` - Aide complète

---

## ⚙️ Configuration Technique

| Paramètre | Valeur |
|-----------|--------|
| **Plateforme** | Render.com |
| **Port** | 10000 (auto-configuré) |
| **Python** | 3.11.0 |
| **Timezone** | Africa/Porto-Novo (UTC+1) |
| **Export auto** | 00h59 chaque jour |
| **Reset auto** | 01h00 chaque jour |
| **Import auto Projet 2** | Après export Projet 1 |

---

## 📥 Format Excel Requis (Projet 2)

Votre fichier Excel doit avoir cette structure:

| Date & Heure | Numéro | Victoire (Joueur/Banquier) |
|--------------|--------|----------------------------|
| 03/01/2025 - 14:20 | 881 | Banquier |
| 03/01/2025 - 14:26 | 886 | Joueur |
| 03/01/2025 - 14:40 | 891 | Joueur |

**⚠️ Important:** Les numéros consécutifs (ex: 56→57) sont automatiquement filtrés à l'import.

---

## 🎯 Critères d'Enregistrement (Projet 1)

### ✅ **Parties enregistrées:**
- Premier groupe: **exactement 3 cartes de couleurs différentes**
- Deuxième groupe: **PAS 3 cartes**
- Gagnant identifiable: **Joueur** ou **Banquier**
- Message finalisé avec symbole **✅**

### ❌ **Parties ignorées:**
- Match nul
- Les deux groupes ont 3 cartes
- Numéros consécutifs (N puis N+1)
- Messages en cours (symbole ⏰)
- Messages avec symbole 🔰

---

## 🔄 Workflow Quotidien Automatique

**À 00h59 (Heure Bénin UTC+1):**
1. 📊 Export Excel Projet 1
2. 📤 Envoi fichier à l'admin
3. 📥 **Import automatique dans Projet 2** (remplacement)
4. 💬 Message de confirmation import

**À 01h00:**
5. 🔄 Reset base de données Projet 1
6. ✅ Système prêt pour nouvelle journée

---

## 🛠️ Dépannage

### **Problème: Bot ne démarre pas**
- ✅ Vérifiez que toutes les variables d'environnement sont définies
- ✅ Vérifiez les logs dans Render.com
- ✅ Assurez-vous que le port 10000 est bien configuré

### **Problème: Prédictions Excel non lancées**
- ✅ Vérifiez que le canal source est configuré avec `/set_channel`
- ✅ Vérifiez que le canal d'affichage est configuré avec `/set_display`
- ✅ Vérifiez le format du fichier Excel

### **Problème: Export quotidien ne fonctionne pas**
- ✅ Vérifiez que la timezone est bien Africa/Porto-Novo (UTC+1)
- ✅ Vérifiez les logs à 00h59 et 01h00
- ✅ Assurez-vous que des parties ont été enregistrées

---

## 📞 Support

**Développé par:** Sossou Kouamé Appolinaire  
**Package créé le:** {timestamp}  
**Version:** duo Final  
**Optimisé pour:** Render.com - Port 10000

---

## ✅ Checklist de Déploiement

Avant de déployer, vérifiez:

- [ ] Repository GitHub créé
- [ ] Tous les fichiers du package uploadés
- [ ] Variables d'environnement configurées sur Render.com
- [ ] Port 10000 confirmé dans render.yaml
- [ ] Service web créé sur Render.com
- [ ] Déploiement réussi (vérifier les logs)
- [ ] Bot répond à `/start` sur Telegram
- [ ] Canal source configuré avec `/set_channel`
- [ ] Canal affichage configuré avec `/set_display`

**🎉 Le bot est prêt à fonctionner 24/7 sur Render.com!**"""
            
            zipf.writestr('README.md', readme)
            logger.info("  ✅ Ajouté: README.md")

        file_size = os.path.getsize(package_name) / 1024
        
        caption = f"""✅ **Package "duo Final" créé avec succès!**

📅 {now_benin.strftime('%d/%m/%Y %H:%M:%S')} (Bénin UTC+1)
📁 duo Final.zip ({file_size:.1f} KB)
🚀 **Optimisé pour Render.com - Port 10000**

**📦 Contenu Complet:**
✅ Projet 1: Stockage de résultats
✅ Projet 2: Système de prédictions Excel
✅ render.yaml (déploiement automatique)
✅ Procfile + runtime.txt
✅ Configuration complète
✅ README détaillé

**📂 Fichiers inclus:**
• main.py (projets fusionnés)
• game_results_manager.py
• yaml_manager.py
• predictor.py
• excel_importer.py
• render.yaml
• Procfile
• runtime.txt
• requirements.txt
• bot_config.json
• .env.example
• README.md
• data/.gitkeep

**🚀 Déploiement Render.com:**
1. Upload sur GitHub
2. Connecter à Render.com
3. Configurer variables d'environnement:
   • API_ID, API_HASH, BOT_TOKEN, ADMIN_ID
4. Déployer automatiquement!

**🔄 Workflow Quotidien (00h59 UTC+1):**
• Export Excel Projet 1
• Import automatique Projet 2
• Reset base Projet 1

Le bot tournera 24/7 sur le port 10000! 🎉"""

        await client.send_file(
            event.chat_id,
            package_name,
            caption=caption
        )
        
        logger.info(f"✅ Package 'duo Final.zip' créé pour Render.com: {file_size:.1f} KB")
        
    except Exception as e:
        logger.error(f"❌ Erreur création duo Final: {e}")
        await event.respond(f"❌ Erreur: {e}")


@client.on(events.NewMessage(pattern='/help'))
async def cmd_help(event):
    """Affiche l'aide"""
    if event.is_group or event.is_channel:
        return

    help_msg = """📖 **AIDE - Bot de Stockage de Résultats de Jeux**

**Fonctionnement:**
Le bot surveille un canal et stocke automatiquement les parties qui remplissent ces critères:

✅ **Critères d'enregistrement:**
• Le premier groupe de parenthèses contient exactement 3 cartes différentes
• Le deuxième groupe ne contient PAS 3 cartes
• Un gagnant est clairement identifiable (Joueur ou Banquier)

❌ **Cas ignorés:**
• Matchs nuls
• Les deux groupes ont 3 cartes
• Pas de numéro de jeu identifiable

**Commandes Projet 1 (Stockage):**
• `/start` - Message de bienvenue
• `/status` - Voir les statistiques
• `/fichier` - Exporter en fichier Excel manuellement
• `/deploy` - Créer un package pour déployer sur Replit
• `/reset` - Remettre à zéro la base de données manuellement
• `/stop_transfer` - Désactiver le transfert des messages du canal
• `/start_transfer` - Réactiver le transfert des messages du canal
• `/set_channel <ID>` - Configurer le canal source

**Commandes Projet 2 (Prédictions):**
• `/set_display <ID>` - Configurer le canal d'affichage
• `/stats_excel` - Statistiques des prédictions Excel
• `/clear_excel` - Effacer toutes les prédictions
• `/deploy_duo2` - Créer package DUO2 (Projet 1 + 2)
• Envoyer fichier Excel - Import automatique des prédictions

• `/help` - Afficher cette aide

**Export automatique:**
• Remise à zéro automatique à 1h00 du matin (heure Bénin UTC+1) chaque jour

**Configuration:**
1. Ajoutez le bot à votre canal Telegram
2. Utilisez la commande `/set_channel ID` en message privé
3. Le bot commencera à surveiller automatiquement

**Format attendu des messages:**
Les messages doivent contenir:
• Un numéro de jeu (#N123 ou similaire)
• Deux groupes entre parenthèses: (cartes) - (cartes)
• Une indication du gagnant (Joueur/Banquier)

**Support:**
Pour toute question, contactez l'administrateur."""

    await event.respond(help_msg)


async def index(request):
    """Page d'accueil du bot"""
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Bot Telegram - Résultats de Jeux</title>
        <meta charset="utf-8">
    </head>
    <body>
        <h1>🤖 Bot Telegram - Stockage de Résultats</h1>
        <p>Le bot est en ligne et fonctionne correctement.</p>
        <ul>
            <li><a href="/health">Health Check</a></li>
            <li><a href="/status">Statut et Statistiques (JSON)</a></li>
        </ul>
    </body>
    </html>
    """
    return web.Response(text=html, content_type='text/html', status=200)


async def health_check(request):
    """Endpoint de vérification de santé"""
    return web.Response(text="OK", status=200)


async def status_api(request):
    """Endpoint de statut"""
    stats = results_manager.get_stats()
    status_data = {
        "status": "running",
        "channel_configured": detected_stat_channel is not None,
        "channel_id": detected_stat_channel,
        "stats": stats,
        "timestamp": datetime.now().isoformat()
    }
    return web.json_response(status_data)


async def start_web_server():
    """Démarre le serveur web en arrière-plan"""
    app = web.Application()
    app.router.add_get('/', index)
    app.router.add_get('/health', health_check)
    app.router.add_get('/status', status_api)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', PORT)
    await site.start()
    logger.info(f"✅ Serveur web démarré sur le port {PORT}")


auto_export_task = None


async def daily_reset():
    """Remise à zéro quotidienne à 00h59 du matin (heure du Bénin UTC+1)"""
    while True:
        try:
            benin_tz = timezone(timedelta(hours=1))
            now_benin = datetime.now(benin_tz)
            next_reset_benin = now_benin.replace(hour=0, minute=59, second=0, microsecond=0)

            if now_benin.hour >= 1 or (now_benin.hour == 0 and now_benin.minute >= 59):
                next_reset_benin += timedelta(days=1)

            wait_seconds = (next_reset_benin - now_benin).total_seconds()
            logger.info(f"⏰ Prochaine remise à zéro dans {wait_seconds/3600:.1f} heures (à 00h59 heure Bénin)")

            await asyncio.sleep(wait_seconds)

            logger.info("🔄 REMISE À ZÉRO QUOTIDIENNE À 00H59...")

            stats = results_manager.get_stats()

            if stats['total'] > 0:
                date_str = (now_benin - timedelta(days=1)).strftime('%d-%m-%Y')
                file_path = f"resultats_journee_{date_str}.xlsx"
                excel_file = results_manager.export_to_txt(file_path=file_path)

                if excel_file and os.path.exists(excel_file):
                    caption = f"""📊 **Rapport Journalier du {date_str}**

📈 Résultats de la journée (01h00 à 00h59):
• Total: {stats['total']} parties
• Victoires Joueur: {stats['joueur_victoires']} ({stats['taux_joueur']:.1f}%)
• Victoires Banquier: {stats['banquier_victoires']} ({stats['taux_banquier']:.1f}%)

🔄 La base de données va être remise à zéro pour une nouvelle journée."""

                    await client.send_file(
                        ADMIN_ID,
                        excel_file,
                        caption=caption
                    )
                    logger.info(f"✅ Rapport journalier envoyé avec {stats['total']} parties")
            else:
                await client.send_message(
                    ADMIN_ID,
                    "📊 **Rapport Journalier**\n\nAucune partie enregistrée aujourd'hui (01h00 à 00h59)."
                )
                logger.info("ℹ️ Aucune donnée à exporter pour aujourd'hui")

            # ✅ NOUVEAU : Importer automatiquement dans le Projet 2
            if excel_file and os.path.exists(excel_file):
                logger.info("📥 Import automatique du fichier Excel dans le Projet 2...")
                import_result = excel_manager.import_excel(excel_file, replace_mode=True)
                
                if import_result['success']:
                    consecutive_info = f", {import_result.get('consecutive_skipped', 0)} consécutifs ignorés" if import_result.get('consecutive_skipped', 0) > 0 else ""
                    logger.info(f"✅ Import automatique réussi: {import_result['imported']} prédictions importées{consecutive_info}")
                    
                    import_msg = f"""
📥 **Import Automatique dans Projet 2**

✅ Fichier Excel importé avec succès!
• Prédictions importées: {import_result['imported']}
• Anciennes remplacées: {import_result.get('old_count', 0)}
• Consécutifs ignorés: {import_result.get('consecutive_skipped', 0)}
• Total en base: {import_result['total']}

Le système est prêt pour la nouvelle journée! 🎉"""
                    
                    await client.send_message(ADMIN_ID, import_msg)
                else:
                    logger.error(f"❌ Erreur import automatique: {import_result.get('error', 'Inconnue')}")
                    await client.send_message(
                        ADMIN_ID,
                        f"⚠️ **Erreur import automatique Projet 2**\n\n{import_result.get('error', 'Erreur inconnue')}"
                    )

            results_manager._save_yaml([])
            logger.info("✅ Base de données remise à zéro")

            await client.send_message(
                ADMIN_ID,
                "🔄 **Remise à zéro effectuée à 00h59**\n\nLa base de données est maintenant vide et prête pour une nouvelle journée d'enregistrement."
            )

        except asyncio.CancelledError:
            logger.info("🛑 Tâche de remise à zéro arrêtée")
            break
        except Exception as e:
            logger.error(f"❌ Erreur remise à zéro: {e}")
            await asyncio.sleep(3600)


# ==================== COMMANDES PROJET 2 ====================

@client.on(events.NewMessage(pattern='/set_display'))
async def set_display_channel(event):
    """Configure le canal d'affichage des prédictions (Projet 2)"""
    global detected_display_channel
    
    try:
        if event.is_group or event.is_channel:
            return
            
        if event.sender_id != ADMIN_ID:
            await event.respond("❌ Seul l'administrateur peut configurer les canaux")
            return
            
        parts = event.message.message.split()
        if len(parts) < 2:
            await event.respond("❌ Usage: /set_display <channel_id>")
            return
            
        channel_id = int(parts[1])
        detected_display_channel = channel_id
        save_config()
        
        await event.respond(f"✅ Canal d'affichage configuré: {channel_id}")
        logger.info(f"✅ Canal d'affichage configuré: {channel_id}")
        
    except Exception as e:
        logger.error(f"❌ Erreur set_display_channel: {e}")
        await event.respond(f"❌ Erreur: {e}")


@client.on(events.NewMessage())
async def handle_excel_file(event):
    """Gestion de l'import de fichier Excel (Projet 2)"""
    try:
        if event.media and hasattr(event.media, 'document'):
            doc = event.media.document
            if doc.mime_type in ['application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 'application/vnd.ms-excel']:
                file_path = await event.download_media()
                
                result = excel_manager.import_excel(file_path, replace_mode=True)
                
                if result['success']:
                    stats_msg = f"""✅ **Import Excel réussi (REMPLACEMENT)**

📊 **Résultat**:
• Importées: {result['imported']}
• Ignorées (déjà lancées): {result['skipped']}
• Ignorées (consécutives): {result['consecutive_skipped']}
• Total dans la base: {result['total']}

Mode: {result['mode']}"""
                    
                    if result.get('old_count'):
                        stats_msg += f"\n• Anciennes prédictions: {result['old_count']}"
                        
                    await event.respond(stats_msg)
                else:
                    await event.respond(f"❌ Erreur import: {result['error']}")
                    
                if os.path.exists(file_path):
                    os.remove(file_path)
                    
    except Exception as e:
        logger.error(f"❌ Erreur handle_excel_file: {e}")


@client.on(events.NewMessage(pattern='/stats_excel'))
async def stats_excel_command(event):
    """Affiche les statistiques des prédictions Excel (Projet 2)"""
    try:
        stats = excel_manager.get_stats()
        pending = excel_manager.get_pending_predictions()[:5]
        
        msg = f"""📊 **Statistiques Prédictions Excel**

• Total: {stats['total']}
• Lancées: {stats['launched']}
• En attente: {stats['pending']}

**Prochaines prédictions:**"""
        
        for pred in pending:
            msg += f"\n• #{pred['numero']}: {pred['victoire']}"
            
        await event.respond(msg)
        
    except Exception as e:
        logger.error(f"❌ Erreur stats_excel: {e}")
        await event.respond(f"❌ Erreur: {e}")


@client.on(events.NewMessage(pattern='/clear_excel'))
async def clear_excel_command(event):
    """Efface toutes les prédictions Excel (Projet 2)"""
    if event.sender_id != ADMIN_ID:
        await event.respond("❌ Seul l'administrateur peut effacer les prédictions")
        return
        
    try:
        excel_manager.clear_predictions()
        await event.respond("✅ Toutes les prédictions Excel ont été effacées")
        
    except Exception as e:
        logger.error(f"❌ Erreur clear_excel: {e}")
        await event.respond(f"❌ Erreur: {e}")


async def main():
    """Fonction principale"""
    try:
        await start_web_server()

        success = await start_bot()
        if not success:
            logger.error("❌ Échec du démarrage du bot")
            return

        logger.info("✅ Bot complètement opérationnel")
        logger.info("📊 En attente de messages...")

        asyncio.create_task(daily_reset())
        logger.info("✅ Tâche de remise à zéro démarrée")

        await client.run_until_disconnected()

    except Exception as e:
        logger.error(f"❌ Erreur dans main: {e}")
    finally:
        await client.disconnect()


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 Bot arrêté par l'utilisateur")
    except Exception as e:
        logger.error(f"❌ Erreur fatale: {e}")
