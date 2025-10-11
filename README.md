# 📦 Package "Render Final V2" - Bot Telegram Render.com

📅 **Créé le:** 11/10/2025 à 00:53:00 (Heure Bénin UTC+1)
📦 **Version:** 2025-10-11_00-53-00 - V2
🚀 **Optimisé pour:** Render.com (Port 10000) avec StringSession

---

## 🆕 Nouveautés Version 2

### **Format d'affichage des prédictions:**
- Format: 🔵{numéro} 👗 𝐕𝟏/𝐕𝟐👗 statut: ⏳
- 𝐕𝟏 = Joueur
- 𝐕𝟐 = Banquier
- Statuts: ⏳ (attente), ✅0️⃣/✅1️⃣/✅2️⃣ (succès), ⭕✍🏻 (échec)

### **Notifications désactivées:**
- Plus de notification admin lors du lancement des prédictions
- Messages uniquement dans le canal d'affichage

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
- 🎨 Format compact: 🔵{numéro} 👗 𝐕𝟏/𝐕𝟐👗
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

### **Étape 1: Obtenir la Session Telegram**
1. Lancez le bot localement une première fois
2. Copiez la valeur TELEGRAM_SESSION affichée dans les logs
3. Gardez cette valeur pour l'étape 3

### **Étape 2: Créer un Repository GitHub**
1. Allez sur [github.com](https://github.com)
2. Créez un nouveau repository (public ou privé)
3. Uploadez **TOUS** les fichiers du package "render_final.zip"

### **Étape 3: Connecter à Render.com**
1. Allez sur [render.com](https://render.com)
2. Cliquez sur **"New +"** → **"Web Service"**
3. Connectez votre repository GitHub
4. Render détectera automatiquement `render.yaml`

### **Étape 4: Configurer les Variables d'Environnement**
Dans la section **Environment** de Render.com, ajoutez:

| Variable | Valeur | Où l'obtenir |
|----------|--------|--------------|
| **PORT** | 10000 | Déjà configuré automatiquement |
| **API_ID** | Votre ID | https://my.telegram.org |
| **API_HASH** | Votre Hash | https://my.telegram.org |
| **BOT_TOKEN** | Token du bot | @BotFather sur Telegram |
| **ADMIN_ID** | Votre ID Telegram | @userinfobot sur Telegram |
| **TELEGRAM_SESSION** | Session string | Copié depuis l'étape 1 |

⚠️ **IMPORTANT:** Sans TELEGRAM_SESSION, le bot s'arrêtera après 10 minutes!

### **Étape 5: Déployer**
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
- `/deploy_duo2` - Créer package "Render Final" (Projet 1 + 2)
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
**Package créé le:** 2025-10-11_00-53-00  
**Version:** Render Final  
**Optimisé pour:** Render.com - Port 10000 avec StringSession

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

**🎉 Le bot est prêt à fonctionner 24/7 sur Render.com!**