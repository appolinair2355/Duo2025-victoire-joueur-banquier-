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
from excel_importer import ExcelPredictionManager
from aiohttp import web
from pathlib import Path

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
    PORT = int(os.getenv('PORT') or '5000')

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
prediction_display_channel = -1002999811353  # Canal pour les prédictions
confirmation_pending = {}
transfer_enabled = True
last_generated_excel = None  # Stocke le dernier fichier Excel généré

# Gestionnaires
yaml_manager = YAMLDataManager()
results_manager = GameResultsManager()
excel_manager = ExcelPredictionManager()

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
                # Ignorer les messages qui ne sont pas finalisés et qui ne sont pas des commandes ou des messages traités par le bot
                if '✅' not in message_text and '⏰' not in message_text and event.chat_id == detected_stat_channel:
                    logger.info(f"⚠️ Message ignoré (non finalisé): {info}")
                    return
                elif '✅' not in message_text and event.chat_id == detected_stat_channel:
                    logger.info(f"⚠️ Message ignoré (non finalisé): {info}")
                    return
                else:
                    logger.info(f"⚠️ Message ignoré: {info}")

            # === LOGIQUE EXCEL PREDICTIONS ===
            try:
                import re
                game_number_match = re.search(r'#[NnRr]?(\d+)', message_text)

                if game_number_match:
                    game_number = int(game_number_match.group(1))
                    
                    # 2. Lancer automatiquement les prédictions proches
                    close_pred = excel_manager.find_close_prediction(game_number, tolerance=4)
                    if close_pred and prediction_display_channel:
                        pred_key = close_pred["key"]
                        pred_data = close_pred["prediction"]
                        pred_numero = pred_data["numero"]
                        victoire_type = pred_data["victoire"]

                        v_format = excel_manager.get_prediction_format(victoire_type)
                        prediction_msg = f"🔵{pred_numero} {v_format}statut :⏳"

                        try:
                            sent_msg = await client.send_message(prediction_display_channel, prediction_msg)
                            excel_manager.mark_as_launched(pred_key, sent_msg.id, prediction_display_channel)
                            logger.info(f"🚀 Prédiction Excel #{pred_numero} lancée (écart +{pred_numero - game_number})")
                        except Exception as e:
                            logger.error(f"❌ Erreur envoi prédiction #{pred_numero}: {e}")

                    # 3. Vérifier les prédictions Excel lancées (messages finalisés OU matchs nuls)
                    if ('✅' in message_text or '🔰' in message_text) and '⏰' not in message_text:
                        for key, pred in list(excel_manager.predictions.items()):
                            if not pred["launched"] or pred.get("verified", False):
                                continue

                            pred_numero = pred["numero"]
                            expected_winner = pred["victoire"]

                            # Calculer l'offset réel depuis le numéro de jeu
                            real_offset = game_number - pred_numero

                            # Si le jeu est avant la prédiction, continuer à attendre
                            if real_offset < 0:
                                continue

                            # Si l'offset dépasse 2, marquer comme échec
                            if real_offset > 2:
                                msg_id = pred.get("message_id")
                                channel_id = pred.get("channel_id")
                                if msg_id and channel_id:
                                    v_format = excel_manager.get_prediction_format(expected_winner)
                                    new_text = f"🔵{pred_numero} {v_format}statut :⭕✍🏻"
                                    try:
                                        await client.edit_message(channel_id, msg_id, new_text)
                                        pred["verified"] = True
                                        excel_manager.save_predictions()
                                        logger.info(f"⭕ Prédiction Excel #{pred_numero}: échec (offset {real_offset} > 2)")
                                    except Exception as e:
                                        logger.error(f"❌ Erreur mise à jour échec #{pred_numero}: {e}")
                                continue

                            # Vérifier avec l'offset réel (0, 1 ou 2)
                            # Match nul (🔰) → None, True → Continue sans arrêt
                            status, should_stop = excel_manager.verify_excel_prediction(
                                game_number, message_text, pred_numero, expected_winner, real_offset
                            )

                            if status:
                                # Résultat trouvé (✅0️⃣, ✅1️⃣, ✅2️⃣, ou ❌) → ARRÊT
                                msg_id = pred.get("message_id")
                                channel_id = pred.get("channel_id")

                                if msg_id and channel_id:
                                    v_format = excel_manager.get_prediction_format(expected_winner)
                                    new_text = f"🔵{pred_numero} {v_format}statut :{status}"

                                    try:
                                        await client.edit_message(channel_id, msg_id, new_text)
                                        pred["verified"] = True
                                        excel_manager.save_predictions()
                                        logger.info(f"✅ Prédiction Excel #{pred_numero}: {status} (offset {real_offset})")
                                    except Exception as e:
                                        logger.error(f"❌ Erreur mise à jour prédiction #{pred_numero}: {e}")
                            # Si status est None et should_stop est True → match nul, on continue avec le prochain jeu

            except Exception as e:
                logger.error(f"❌ Erreur logique Excel: {e}")

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

            # Ne traiter que les messages finalisés pour la logique de résultats
            if '✅' not in message_text and '⏰' not in message_text:
                logger.info("⚠️ Message édité ignoré (non finalisé)")
                return

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
    global last_generated_excel

    if event.is_group or event.is_channel:
        return

    if event.sender_id != ADMIN_ID:
        await event.respond("❌ Commande réservée à l'administrateur")
        return

    try:
        await event.respond("📊 Génération du fichier Excel en cours...")
        file_path = results_manager.export_to_txt()

        if file_path and os.path.exists(file_path):
            last_generated_excel = file_path

            await client.send_file(
                event.chat_id,
                file_path,
                caption="📊 **Export des résultats**\n\nFichier Excel généré avec succès!\n\n🎯 Ce fichier sera automatiquement utilisé pour les prédictions."
            )
            logger.info("✅ Fichier Excel exporté et envoyé")

            # Auto-importer pour les prédictions
            await auto_import_excel(file_path)
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
            'yaml_manager.py',
            'excel_importer.py',
            'predictor.py'
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

### 📊 Stockage des résultats
- ✅ **Détection automatique**: Reconnaît les parties avec 3 cartes différentes
- ✅ **Export quotidien**: Génère un fichier Excel à 00h59 (UTC+1)
- ✅ **Réinitialisation auto**: Reset automatique à 01h00
- ✅ **Statistiques en temps réel**: Taux de victoire Joueur/Banquier

### 🎯 Prédictions Excel (intégrées)
- ✅ **Import Excel**: Importation de prédictions depuis fichiers .xlsx
- ✅ **Lancement automatique**: Détection proximité 0-4 parties d'écart
- ✅ **Vérification offsets**: Validation avec offsets 0, 1, 2
- ✅ **Filtrage consécutifs**: Ignore automatiquement les numéros consécutifs
- ✅ **Statuts visuels**: ⏳ En attente, ✅0️⃣/✅1️⃣/✅2️⃣ Réussi, ⭕✍🏻 Échec

## 📊 Commandes disponibles

### Commandes générales
- `/start` - Démarrer le bot et voir les informations
- `/status` - Voir les statistiques actuelles
- `/fichier` - Exporter les résultats en Excel
- `/reset` - Réinitialiser la base de données manuellement
- `/deploy` - Créer un nouveau package de déploiement
- `/help` - Afficher l'aide complète

### Commandes prédictions Excel (Admin)
- **Envoyer fichier .xlsx** - Importer des prédictions Excel
- `/excel_status` - Statut des prédictions Excel
- `/excel_clear` - Effacer toutes les prédictions
- `/sta` - Statistiques rapides Excel

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

        deploy_zip = "duo2025.zip"
        with zipfile.ZipFile(deploy_zip, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(deploy_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, deploy_dir)
                    zipf.write(file_path, arcname)

        short_caption = f"""📦 **Package Render.com - duo2025**

📅 {now_benin.strftime('%d/%m/%Y %H:%M:%S')} (Bénin)
📁 duo2025.zip

**Fonctionnalités incluses:**
✅ Stockage résultats de jeux
✅ Prédictions Excel intégrées
✅ Export automatique à 00h59
✅ Reset automatique à 01h00
✅ Port 10000 configuré

**Fichiers:** main.py, game_results_manager.py, yaml_manager.py, excel_importer.py, predictor.py"""

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

**Commandes:**
• `/start` - Message de bienvenue
• `/status` - Voir les statistiques
• `/fichier` - Exporter en fichier Excel manuellement
• `/deploy` - Créer un package pour déployer sur Replit
• `/reset` - Remettre à zéro la base de données manuellement
• `/stop_transfer` - Désactiver le transfert des messages du canal
• `/start_transfer` - Réactiver le transfert des messages du canal
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


# === HANDLERS EXCEL PREDICTIONS ===

async def auto_import_excel(file_path: str):
    """Auto-importe un fichier Excel pour les prédictions"""
    global last_generated_excel

    try:
        logger.info(f"📥 Auto-import du fichier Excel: {file_path}")

        result = excel_manager.import_excel(file_path)

        if result["success"]:
            last_generated_excel = file_path
            msg = f"""✅ **Auto-Import Excel réussi !**

🔄 **Anciennes prédictions REMPLACÉES**

📊 **Statistiques d'import:**
• Prédictions importées: {result['imported']}
• Déjà lancées (ignorées): {result['skipped']}
• Consécutives (ignorées): {result['consecutive_skipped']}
• **Total actuel**: {result['total']} prédictions

🎯 Les prédictions seront envoyées automatiquement au canal de prédiction."""

            await client.send_message(ADMIN_ID, msg)
            logger.info(f"✅ Auto-import Excel: {result['imported']} prédictions, {result['consecutive_skipped']} consécutives ignorées")
        else:
            await client.send_message(ADMIN_ID, f"❌ Erreur auto-import: {result['error']}")
            logger.error(f"❌ Erreur auto-import Excel: {result['error']}")

    except Exception as e:
        logger.error(f"❌ Erreur auto_import_excel: {e}")


@client.on(events.NewMessage())
async def handle_excel_file(event):
    """Handle Excel file upload for predictions"""
    global last_generated_excel

    if event.is_group or event.is_channel:
        return

    if not event.document:
        return

    try:
        file_ext = event.document.attributes[0].file_name if event.document.attributes else ""
        if not file_ext.endswith('.xlsx'):
            return

        await event.respond("📥 Téléchargement du fichier Excel en cours...")

        file_path = await event.download_media()
        last_generated_excel = file_path

        await event.respond("📊 Import des prédictions en cours...")
        result = excel_manager.import_excel(file_path)

        if result["success"]:
            msg = f"""✅ **Import Excel réussi !**

🔄 **Anciennes prédictions REMPLACÉES**

📊 **Statistiques d'import:**
• Prédictions importées: {result['imported']}
• Déjà lancées (ignorées): {result['skipped']}
• Consécutives (ignorées): {result['consecutive_skipped']}
• **Total actuel**: {result['total']} prédictions

🎯 Les prédictions seront envoyées au canal: {prediction_display_channel}"""
            await event.respond(msg)
            logger.info(f"✅ Import Excel: {result['imported']} prédictions, {result['consecutive_skipped']} consécutives ignorées")
        else:
            await event.respond(f"❌ Erreur lors de l'import: {result['error']}")
            logger.error(f"❌ Erreur import Excel: {result['error']}")

        # Ne pas supprimer le fichier pour pouvoir le réutiliser
        # if os.path.exists(file_path):
        #     os.remove(file_path)

    except Exception as e:
        logger.error(f"❌ Erreur traitement fichier Excel: {e}")
        await event.respond(f"❌ Erreur: {e}")


@client.on(events.NewMessage(pattern='/excel_status'))
async def cmd_excel_status(event):
    """Affiche le statut des prédictions Excel"""
    if event.is_group or event.is_channel:
        return

    if event.sender_id != ADMIN_ID:
        await event.respond("❌ Commande réservée à l'administrateur")
        return

    try:
        stats = excel_manager.get_stats()
        pending = excel_manager.get_pending_predictions()

        msg = f"""📊 **Statut Prédictions Excel**

**Statistiques:**
• Total: {stats['total']}
• Lancées: {stats['launched']}
• En attente: {stats['pending']}

**Prochaines prédictions:**"""

        if pending:
            for i, pred in enumerate(pending[:5], 1):
                msg += f"\n{i}. #{pred['numero']} - {pred['victoire']}"
            if len(pending) > 5:
                msg += f"\n... et {len(pending) - 5} autres"
        else:
            msg += "\n_Aucune prédiction en attente_"

        msg += "\n\n💡 Envoyez un fichier .xlsx pour importer de nouvelles prédictions"

        await event.respond(msg)

    except Exception as e:
        logger.error(f"❌ Erreur excel_status: {e}")
        await event.respond(f"❌ Erreur: {e}")


@client.on(events.NewMessage(pattern='/excel_clear'))
async def cmd_excel_clear(event):
    """Efface toutes les prédictions Excel"""
    if event.is_group or event.is_channel:
        return

    if event.sender_id != ADMIN_ID:
        await event.respond("❌ Commande réservée à l'administrateur")
        return

    try:
        excel_manager.clear_predictions()
        await event.respond("🗑️ **Prédictions Excel effacées**\n\nToutes les prédictions Excel ont été supprimées.")
        logger.info("🗑️ Prédictions Excel effacées")

    except Exception as e:
        logger.error(f"❌ Erreur excel_clear: {e}")
        await event.respond(f"❌ Erreur: {e}")


@client.on(events.NewMessage(pattern='/sta'))
async def cmd_sta(event):
    """Affiche les statistiques Excel simplifiées"""
    if event.is_group or event.is_channel:
        return

    if event.sender_id != ADMIN_ID:
        await event.respond("❌ Commande réservée à l'administrateur")
        return

    try:
        stats = excel_manager.get_stats()
        await event.respond(f"📊 Excel: {stats['total']} total | {stats['launched']} lancées | {stats['pending']} en attente")

    except Exception as e:
        logger.error(f"❌ Erreur sta: {e}")
        await event.respond(f"❌ Erreur: {e}")


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
    global last_generated_excel

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
                    # Stocker comme dernier Excel généré pour auto-import
                    last_generated_excel = excel_file

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

                    # Auto-importer le fichier Excel pour les prédictions
                    await auto_import_excel(excel_file)
            else:
                await client.send_message(
                    ADMIN_ID,
                    "📊 **Rapport Journalier**\n\nAucune partie enregistrée aujourd'hui (01h00 à 00h59)."
                )
                logger.info("ℹ️ Aucune donnée à exporter pour aujourd'hui")

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