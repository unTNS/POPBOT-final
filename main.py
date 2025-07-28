import os
import random
import requests
import discord
import asyncio
from datetime import datetime, time
import pytz
import re
from discord.ext import commands
from discord.ui import View, Button
from discord import app_commands
from flask import Flask
import threading

app = Flask(__name__)

@app.route('/')
def health_check():
    return "Bot is running!"

def run_flask():
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))

# Démarrer Flask dans un thread séparé
flask_thread = threading.Thread(target=run_flask)
flask_thread.daemon = True
flask_thread.start()

# Données en mémoire
economy = {}        # {user_id: argent}
inventaire = {}     # {user_id: [objets]}
xp_data = {}        # {user_id: {"xp": int, "niveau": int}}
xp = {}             # Pour compatibilité avec le nouveau système
niveaux = {}        # Pour compatibilité avec le nouveau système
votes = {}          # {user_id: [choix]}
results = {}

# Objets / tickets
OBJETS = {
    "double_vote": {"emoji": "🎟️", "prix": 5000, "desc": "Permet de voter deux fois"},
    "ticket_special": {"emoji": "🎫", "prix": 30000, "desc": "Utilisé pour choisir un film via #utilisation-objets"}
}

# Variables pour sondages personnalisés
current_poll = None  # {"title": str, "choices": [str], "votes": {user_id: [choices]}, "results": {choice: count}}

def xp_requise(niveau):
    return 5 * (niveau ** 2) + 50 * niveau + 100

# Initialisation du bot
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"Bot connecté : {bot.user}")
    try:
        synced = await bot.tree.sync()
        print(f"Synchronisé {len(synced)} commande(s) slash")
    except Exception as e:
        print(f"Erreur de synchronisation: {e}")

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    user_id = message.author.id

    # Vérifie si l'utilisateur a le rôle Animateur
    bonus_xp = False
    for role in message.author.roles:
        if role.name.lower() == "animateur":
            bonus_xp = True
            break

    # Gain d'XP (15–25 de base)
    gain = random.randint(15, 25)

    # Bonus x10 si Animateur
    if bonus_xp:
        gain = 10

    # Ajout d'XP et d'argent
    xp[user_id] = xp.get(user_id, 0) + gain
    economy[user_id] = economy.get(user_id, 0) + random.randint(5, 15)

    # Calcul du niveau
    lvl = niveaux.get(user_id, 1)
    xp_necessaire = 100 * lvl
    if xp[user_id] >= xp_necessaire:
        xp[user_id] -= xp_necessaire
        niveaux[user_id] = lvl + 1

        # Récompense tous les 10 niveaux
        if (lvl + 1) % 10 == 0:
            inventaire.setdefault(user_id, []).append("double_vote")
            recompense = discord.utils.get(message.guild.text_channels, name="récompense")
            if recompense:
                await recompense.send(
                    f"🎉 {message.author.mention} a atteint le niveau {lvl + 1} et gagne un objet double_vote !"
                )

        # Annonce de niveau
        salon_niveaux = discord.utils.get(message.guild.text_channels, name="niveaux")
        if salon_niveaux:
            await salon_niveaux.send(
                f"🔼 {message.author.mention} est passé niveau {lvl + 1} !"
            )

    await bot.process_commands(message)

# --- Commandes Slash ---

@bot.tree.command(name="boutique", description="Affiche la boutique du serveur")
async def boutique_slash(interaction: discord.Interaction):
    embed = discord.Embed(title="🛍️ Boutique", color=0x00b0f4)
    for obj, info in OBJETS.items():
        embed.add_field(
            name=f"{info['emoji']} {obj}",
            value=f"💸 {info['prix']} pièces — {info['desc']}",
            inline=False
        )
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="recompenses", description="Affiche les récompenses de niveau")
async def recompenses_slash(interaction: discord.Interaction):
    embed = discord.Embed(title="🏆 Récompenses de niveau", color=0xf4c300)
    embed.add_field(
        name="🎯 Tous les 10 niveaux",
        value=f"Tu gagnes **1 {OBJETS['double_vote']['emoji']} `double_vote`** automatiquement !",
        inline=False
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="niveau", description="Affiche ton niveau et expérience")
async def niveau_slash(interaction: discord.Interaction):
    user_id = interaction.user.id
    xp_actuelle = xp.get(user_id, 0)
    niveau_actuel = niveaux.get(user_id, 1)
    xp_suivant = 100 * niveau_actuel

    embed = discord.Embed(
        title=f"📈 Niveau de {interaction.user.display_name}",
        color=0x7289DA
    )
    embed.add_field(name="Niveau actuel", value=f"**{niveau_actuel}**", inline=True)
    embed.add_field(name="Expérience", value=f"{xp_actuelle}/{xp_suivant} XP", inline=True)
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="balance", description="Affiche ton nombre de pièces")
async def balance_slash(interaction: discord.Interaction):
    argent = economy.get(interaction.user.id, 0)
    embed = discord.Embed(
        title=f"💰 Pièces de {interaction.user.display_name}",
        description=f"Tu as {argent} pièces",
        color=0xFFD700
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="inventaire", description="Affiche ton inventaire")
async def inventaire_slash(interaction: discord.Interaction):
    objets = inventaire.get(interaction.user.id, [])
    embed = discord.Embed(
        title=f"🎒 Inventaire de {interaction.user.display_name}",
        color=0x2ECC71
    )
    if objets:
        desc = []
        compteur = {}
        for obj in objets:
            compteur[obj] = compteur.get(obj, 0) + 1
        for obj, quantite in compteur.items():
            emoji = OBJETS[obj]['emoji'] if obj in OBJETS else ""
            desc.append(f"{emoji} `{obj}` x{quantite}")
        embed.description = "\n".join(desc)
    else:
        embed.description = "Ton inventaire est vide."
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="acheter", description="Achète un objet dans la boutique")
@app_commands.describe(objet="Le nom de l'objet à acheter")
@app_commands.choices(objet=[
    app_commands.Choice(name="🎟️ Double Vote", value="double_vote"),
    app_commands.Choice(name="🎫 Ticket Spécial", value="ticket_special")
])
async def acheter_slash(interaction: discord.Interaction, objet: app_commands.Choice[str]):
    user_id = interaction.user.id
    objet_nom = objet.value

    if objet_nom not in OBJETS:
        await interaction.response.send_message("❌ Cet objet n'existe pas dans la boutique.", ephemeral=True)
        return

    prix = OBJETS[objet_nom]["prix"]
    argent = economy.get(user_id, 0)

    if argent < prix:
        await interaction.response.send_message(f"💸 Tu n'as pas assez de pièces pour acheter {objet_nom}. Il coûte {prix} pièces.", ephemeral=True)
        return

    economy[user_id] = argent - prix
    inventaire.setdefault(user_id, []).append(objet_nom)

    await interaction.response.send_message(f"✅ Tu as acheté {OBJETS[objet_nom]['emoji']} {objet_nom} pour {prix} pièces !", ephemeral=True)

@bot.tree.command(name="utiliser", description="Utilise un objet de ton inventaire")
@app_commands.describe(objet="Le nom de l'objet à utiliser")
@app_commands.choices(objet=[
    app_commands.Choice(name="🎟️ Double Vote", value="double_vote"),
    app_commands.Choice(name="🎫 Ticket Spécial", value="ticket_special")
])
async def utiliser_slash(interaction: discord.Interaction, objet: app_commands.Choice[str]):
    user_id = interaction.user.id
    objet_nom = objet.value

    if objet_nom not in OBJETS:
        await interaction.response.send_message("❌ Cet objet n'existe pas dans la boutique.", ephemeral=True)
        return

    objets = inventaire.get(user_id, [])
    if objet_nom not in objets:
        await interaction.response.send_message(f"❌ Tu n'as pas de {objet_nom} dans ton inventaire.", ephemeral=True)
        return

    # Effets spécifiques des objets
    if objet_nom == "double_vote":
        # Activer le double vote pour l'utilisateur
        global double_vote_utilisateurs
        double_vote_utilisateurs[user_id] = True
        await interaction.response.send_message("🎟️ Double Vote activé ! Tu peux maintenant voter deux fois au prochain sondage.", ephemeral=True)
        inventaire[user_id].remove(objet_nom)  # Consomme l'objet

    elif objet_nom == "ticket_special":
        # Logique pour permettre de choisir un film (peut ouvrir un formulaire)
        # Utilisation de la variable globale
        global ticket_special_utilisateurs
        ticket_special_utilisateurs[user_id] = True
        await interaction.response.send_message("🎫 Ticket Spécial activé ! Ton prochain vote comptera pour 100000000000 votes.", ephemeral=True)
        inventaire[user_id].remove(objet_nom)  # Consomme l'objet
    else:
        await interaction.response.send_message("❌ Cet objet ne peut pas être utilisé.", ephemeral=True)


@bot.tree.command(name="giveargent", description="Donne de l'argent à un membre (Animateurs uniquement)")
@app_commands.describe(membre="Le membre à qui donner l'argent", montant="Le montant à donner")
async def giveargent_slash(interaction: discord.Interaction, membre: discord.Member, montant: int):
    if not any(role.name.lower() == "animateur" for role in interaction.user.roles):
        await interaction.response.send_message("🚫 Seuls les Animateurs peuvent utiliser cette commande.", ephemeral=True)
        return
    if montant <= 0:
        await interaction.response.send_message("❌ Le montant doit être positif.", ephemeral=True)
        return
    economy[membre.id] = economy.get(membre.id, 0) + montant
    embed = discord.Embed(
        title="💸 Argent donné",
        description=f"{interaction.user.mention} a donné {montant} pièces à {membre.mention} !",
        color=0x00cc66
    )
    await interaction.response.send_message(embed=embed)

# --- Commandes traditionnelles (gardées pour compatibilité) ---

@bot.command(aliases=['boutique'])
async def shop(ctx):
    embed = discord.Embed(title="🛍️ Boutique", color=0x00b0f4)
    for obj, info in OBJETS.items():
        embed.add_field(
            name=f"{info['emoji']} {obj}",
            value=f"💸 {info['prix']} pièces — {info['desc']}",
            inline=False
        )
    await ctx.send(embed=embed, delete_after=60)

@bot.command()
async def recompenses(ctx):
    embed = discord.Embed(title="🏆 Récompenses de niveau", color=0xf4c300)
    embed.add_field(
        name="🎯 Tous les 10 niveaux",
        value=f"Tu gagnes **1 {OBJETS['double_vote']['emoji']} `double_vote`** automatiquement !",
        inline=False
    )
    await ctx.send(embed=embed)

@bot.command()
async def niveau(ctx):
    user_id = ctx.author.id
    xp_actuelle = xp.get(user_id, 0)
    niveau_actuel = niveaux.get(user_id, 1)
    xp_suivant = 100 * niveau_actuel

    embed = discord.Embed(
        title=f"📈 Niveau de {ctx.author.display_name}",
        color=0x7289DA
    )
    embed.add_field(name="Niveau actuel", value=f"**{niveau_actuel}**", inline=True)
    embed.add_field(name="Expérience", value=f"{xp_actuelle}/{xp_suivant} XP", inline=True)
    await ctx.send(embed=embed)

@bot.command()
async def balance(ctx):
    argent = economy.get(ctx.author.id, 0)
    embed = discord.Embed(
        title=f"💰 Pièces de {ctx.author.display_name}",
        description=f"Tu as {argent} pièces",
        color=0xFFD700
    )
    await ctx.send(embed=embed, delete_after=60)

@bot.command()
async def inventaire_user(ctx):
    objets = inventaire.get(ctx.author.id, [])
    embed = discord.Embed(
        title=f"🎒 Inventaire de {ctx.author.display_name}",
        color=0x2ECC71
    )
    if objets:
        desc = []
        compteur = {}
        for obj in objets:
            compteur[obj] = compteur.get(obj, 0) + 1
        for obj, quantite in compteur.items():
            emoji = OBJETS[obj]['emoji'] if obj in OBJETS else ""
            desc.append(f"{emoji} `{obj}` x{quantite}")
        embed.description = "\n".join(desc)
    else:
        embed.description = "Ton inventaire est vide."
    await ctx.send(embed=embed)

@bot.command()
async def acheter(ctx, objet_nom: str):
    user_id = ctx.author.id
    objet_nom = objet_nom.lower()

    if objet_nom not in OBJETS:
        await ctx.send("❌ Cet objet n'existe pas dans la boutique.", delete_after=10)
        return

    prix = OBJETS[objet_nom]["prix"]
    argent = economy.get(user_id, 0)

    if argent < prix:
        await ctx.send(f"💸 Tu n'as pas assez de pièces pour acheter {objet_nom}. Il coûte {prix} pièces.", delete_after=10)
        return

    economy[user_id] = argent - prix
    inventaire.setdefault(user_id, []).append(objet_nom)

    await ctx.send(f"✅ Tu as acheté {OBJETS[objet_nom]['emoji']} {objet_nom} pour {prix} pièces !", delete_after=15)

@bot.command()
async def utiliser(ctx, objet_nom: str):
    user_id = ctx.author.id
    objet_nom = objet_nom.lower()

    if objet_nom not in OBJETS:
        await ctx.send("❌ Cet objet n'existe pas dans la boutique.", delete_after=10)
        return

    objets = inventaire.get(user_id, [])
    if objet_nom not in objets:
        await ctx.send(f"❌ Tu n'as pas de {objet_nom} dans ton inventaire.", delete_after=10)
        return

    # Effets spécifiques des objets
    if objet_nom == "double_vote":
        # Activer le double vote pour l'utilisateur
        global double_vote_utilisateurs
        double_vote_utilisateurs[user_id] = True
        await ctx.send("🎟️ Double Vote activé ! Tu peux maintenant voter deux fois au prochain sondage.", delete_after=10)
        inventaire[user_id].remove(objet_nom)  # Consomme l'objet

    elif objet_nom == "ticket_special":
        # Logique pour permettre de choisir un film (peut ouvrir un formulaire)
        # Utilisation de la variable globale
        global ticket_special_utilisateurs
        ticket_special_utilisateurs[user_id] = True
        await ctx.send("🎫 Ticket Spécial activé ! Ton prochain vote comptera pour 1000000000 votes.", delete_after=10)
        inventaire[user_id].remove(objet_nom)  # Consomme l'objet
    else:
        await ctx.send("❌ Cet objet ne peut pas être utilisé.", delete_after=10)

# --- Sondage / Vote ---

class CustomVoteButton(Button):
    def __init__(self, choice, poll_data):
        super().__init__(label=choice, style=discord.ButtonStyle.primary)
        self.choice = choice
        self.poll_data = poll_data

    async def callback(self, interaction: discord.Interaction):
        user = interaction.user
        user_id = user.id

        if not self.poll_data:
            await interaction.response.send_message("❌ Aucun sondage actif.", ephemeral=True)
            return

        # Vérifier si l'utilisateur a un ticket spécial actif
        bonus_votes = 1000000000 if ticket_special_utilisateurs.get(user_id, False) else 0

        # Vérifier si l'utilisateur a le double vote activé
        has_double_vote = double_vote_utilisateurs.get(user_id, False)
        max_votes = 2 if has_double_vote else 1

        if user_id not in self.poll_data["votes"]:
            self.poll_data["votes"][user_id] = []

        # Si l'utilisateur a un ticket spécial, il peut voter même s'il a déjà voté
        if not bonus_votes and len(self.poll_data["votes"][user_id]) >= max_votes:
            await interaction.response.send_message(
                f"❌ Tu as déjà utilisé tes {max_votes} vote(s) !", ephemeral=True
            )
            return

        # Vérifier si l'utilisateur a déjà voté pour ce choix (sauf avec ticket spécial ou double vote)
        if not bonus_votes and not has_double_vote and self.choice in self.poll_data["votes"][user_id]:
            await interaction.response.send_message(
                f"❌ Tu as déjà voté pour {self.choice} !", ephemeral=True
            )
            return

        # Avec le double vote, on peut voter 2 fois max pour le même choix
        if has_double_vote and not bonus_votes:
            vote_count_for_choice = self.poll_data["votes"][user_id].count(self.choice)
            if vote_count_for_choice >= 2:
                await interaction.response.send_message(
                    f"❌ Tu as déjà voté 2 fois pour {self.choice} !", ephemeral=True
                )
                return

        # Ajouter le vote
        vote_count = 100000000000 if bonus_votes else 1
        self.poll_data["votes"][user_id].append(self.choice)
        self.poll_data["results"][self.choice] = self.poll_data["results"].get(self.choice, 0) + vote_count

        if bonus_votes:
            # Désactiver le ticket spécial après utilisation
            ticket_special_utilisateurs[user_id] = False
            await interaction.response.send_message(
                f"🎉 **TICKET SPÉCIAL ACTIVÉ** ! Ton vote pour **{self.choice}** compte pour **100000000000 votes** !",
                ephemeral=True
            )
        else:
            # Si c'était le deuxième vote avec double vote, désactiver le double vote
            if has_double_vote and len(self.poll_data["votes"][user_id]) >= 2:
                double_vote_utilisateurs[user_id] = False
                await interaction.response.send_message(
                    f"✅ Tu as voté pour **{self.choice}** ! (Double vote utilisé - 2/2 votes)", ephemeral=True
                )
            else:
                votes_restants = max_votes - len(self.poll_data["votes"][user_id])
                await interaction.response.send_message(
                    f"✅ Tu as voté pour **{self.choice}** ! ({len(self.poll_data['votes'][user_id])}/{max_votes} votes)", ephemeral=True
                )

class CustomVoteView(View):
    def __init__(self, poll_data):
        super().__init__(timeout=None)
        self.poll_data = poll_data

        for choice in poll_data["choices"]:
            self.add_item(CustomVoteButton(choice, poll_data))

@bot.tree.command(name="sondage", description="Crée un sondage avec plusieurs choix")
@app_commands.describe(
    titre="Le titre du sondage",
    choix1="Premier choix",
    choix2="Deuxième choix",
    choix3="Troisième choix (optionnel)",
    choix4="Quatrième choix (optionnel)",
    choix5="Cinquième choix (optionnel)"
)
async def sondage_slash(interaction: discord.Interaction, titre: str, choix1: str, choix2: str, 
                       choix3: str = None, choix4: str = None, choix5: str = None):
    global current_poll

    choices = [choix1, choix2]
    if choix3: choices.append(choix3)
    if choix4: choices.append(choix4)
    if choix5: choices.append(choix5)

    current_poll = {
        "title": titre,
        "choices": choices,
        "votes": {},
        "results": {choice: 0 for choice in choices}
    }

    embed = discord.Embed(
        title=f"🗳️ {titre}",
        description="Clique sur un bouton pour voter !",
        color=0x3498db
    )

    choices_text = "\n".join([f"• {choice}" for choice in choices])
    embed.add_field(name="Choix disponibles:", value=choices_text, inline=False)

    view = CustomVoteView(current_poll)
    await interaction.response.send_message(embed=embed, view=view)

@bot.tree.command(name="resultats", description="Affiche les résultats du sondage en cours")
async def resultats_slash(interaction: discord.Interaction):
    global current_poll

    if not current_poll or not current_poll["results"]:
        await interaction.response.send_message("❌ Aucun sondage en cours.", ephemeral=True)
        return

    embed = discord.Embed(
        title=f"📊 Résultats: {current_poll['title']}",
        color=0x2ecc71
    )

    sorted_results = sorted(current_poll["results"].items(), key=lambda x: x[1], reverse=True)

    results_text = ""
    total_votes = sum(current_poll["results"].values())

    for choice, count in sorted_results:
        percentage = (count / total_votes * 100) if total_votes > 0 else 0
        results_text += f"**{choice}**: {count} vote(s) ({percentage:.1f}%)\n"

    embed.description = results_text
    embed.add_field(name="Total des votes", value=f"{total_votes} vote(s)", inline=False)

    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="stopsondage", description="Arrête le sondage en cours (Animateurs uniquement)")
async def stopsondage_slash(interaction: discord.Interaction):
    global current_poll

    if not any(role.name.lower() == "animateur" for role in interaction.user.roles):
        await interaction.response.send_message("🚫 Seuls les Animateurs peuvent arrêter un sondage.", ephemeral=True)
        return

    if not current_poll:
        await interaction.response.send_message("❌ Aucun sondage en cours.", ephemeral=True)
        return

    embed = discord.Embed(
        title=f"🏁 Sondage terminé: {current_poll['title']}",
        color=0xe74c3c
    )

    sorted_results = sorted(current_poll["results"].items(), key=lambda x: x[1], reverse=True)
    total_votes = sum(current_poll["results"].values())

    results_text = ""
    for choice, count in sorted_results:
        percentage = (count / total_votes * 100) if total_votes > 0 else 0
        results_text += f"**{choice}**: {count} vote(s) ({percentage:.1f}%)\n"

    embed.description = results_text
    embed.add_field(name="Total des votes", value=f"{total_votes} vote(s)", inline=False)

    if sorted_results and sorted_results[0][1] > 0:
        embed.add_field(name="🏆 Gagnant", value=f"**{sorted_results[0][0]}**", inline=False)

    await interaction.response.send_message(embed=embed)
    current_poll = None

# --- Commandes traditionnelles (gardées pour compatibilité) ---

@bot.command()
async def sondage(ctx, *, args):
    """
    Utilisation: !sondage nom:#choix1:#choix2:#choix3:etc
    Exemple: !sondage Quel film regarder ce soir ?:#Harry Potter:#Star Wars:#Le Seigneur des Anneaux
    """
    global current_poll

    try:
        parts = args.split(':#')
        if len(parts) < 3:
            await ctx.send("❌ Format incorrect. Utilise: `!sondage titre:#choix1:#choix2:#choix3`\nExemple: `!sondage Quel film ?:#Option A:#Option B:#Option C`")
            return

        title = parts[0]
        choices = parts[1:]

        if len(choices) > 10:
            await ctx.send("❌ Maximum 10 choix autorisés.")
            return

        current_poll = {
            "title": title,
            "choices": choices,
            "votes": {},
            "results": {choice: 0 for choice in choices}
        }

        embed = discord.Embed(
            title=f"🗳️ {title}",
            description="Clique sur un bouton pour voter !",
            color=0x3498db
        )

        choices_text = "\n".join([f"• {choice}" for choice in choices])
        embed.add_field(name="Choix disponibles:", value=choices_text, inline=False)

        view = CustomVoteView(current_poll)
        await ctx.send(embed=embed, view=view)

    except Exception as e:
        await ctx.send("❌ Erreur dans le format. Utilise: `!sondage titre:#choix1:#choix2:#choix3`")

@bot.command()
async def resultats(ctx):
    global current_poll

    if not current_poll or not current_poll["results"]:
        await ctx.send("❌ Aucun sondage en cours.")
        return

    embed = discord.Embed(
        title=f"📊 Résultats: {current_poll['title']}",
        color=0x2ecc71
    )

    sorted_results = sorted(current_poll["results"].items(), key=lambda x: x[1], reverse=True)

    results_text = ""
    total_votes = sum(current_poll["results"].values())

    for choice, count in sorted_results:
        percentage = (count / total_votes * 100) if total_votes > 0 else 0
        results_text += f"**{choice}**: {count} vote(s) ({percentage:.1f}%)\n"

    embed.description = results_text
    embed.add_field(name="Total des votes", value=f"{total_votes} vote(s)", inline=False)

    await ctx.send(embed=embed)

@bot.command()
async def stopsondage(ctx):
    """Arrête le sondage en cours (réservé aux Animateurs)"""
    global current_poll

    if not any(role.name.lower() == "animateur" for role in ctx.author.roles):
        await ctx.send("🚫 Seuls les Animateurs peuvent arrêter un sondage.")
        return

    if not current_poll:
        await ctx.send("❌ Aucun sondage en cours.")
        return

    embed = discord.Embed(
        title=f"🏁 Sondage terminé: {current_poll['title']}",
        color=0xe74c3c
    )

    sorted_results = sorted(current_poll["results"].items(), key=lambda x: x[1], reverse=True)
    total_votes = sum(current_poll["results"].values())

    results_text = ""
    for choice, count in sorted_results:
        percentage = (count / total_votes * 100) if total_votes > 0 else 0
        results_text += f"**{choice}**: {count} vote(s) ({percentage:.1f}%)\n"

    embed.description = results_text
    embed.add_field(name="Total des votes", value=f"{total_votes} vote(s)", inline=False)

    if sorted_results and sorted_results[0][1] > 0:
        embed.add_field(name="🏆 Gagnant", value=f"**{sorted_results[0][0]}**", inline=False)

    await ctx.send(embed=embed)
    current_poll = None

@bot.command()
async def retireargent(ctx, membre: discord.Member, montant: int):
    # Vérifie que l'auteur a le rôle Animateur
    if not any(role.name.lower() == "animateur" for role in ctx.author.roles):
        await ctx.send("🚫 Tu n'as pas la permission d'utiliser cette commande.")
        return

    if montant <= 0:
        await ctx.send("❌ Le montant doit être positif.")
        return

    user_id = membre.id
    current_balance = economy.get(user_id, 0)

    if current_balance < montant:
        await ctx.send(f"❌ {membre.display_name} n'a pas assez de pièces.")
        return

    economy[user_id] = current_balance - montant

    embed = discord.Embed(
        title="💸 Argent retiré",
        description=f"{ctx.author.mention} a retiré {montant} pièces à {membre.mention}.",
        color=0xFF4444
    )
    await ctx.send(embed=embed)

# Stocke les films déjà montrés pour éviter les doublons
historique = {}

# Genre mapping de nom → ID TMDb
GENRES = {
    "action": 28,
    "aventure": 12,
    "animation": 16,
    "comédie": 35,
    "crime": 80,
    "documentaire": 99,
    "drame": 18,
    "famille": 10751,
    "fantastique": 14,
    "histoire": 36,
    "horreur": 27,
    "musique": 10402,
    "mystère": 9648,
    "romance": 10749,
    "science-fiction": 878,
    "téléfilm": 10770,
    "thriller": 53,
    "guerre": 10752,
    "western": 37
}

def get_film_aleatoire(genre_id, exclus=None):
    # Prend un film aléatoire bien noté (vote_average > 6) parmi les populaires
    page = random.randint(1, 10)
    url = f"https://api.themoviedb.org/3/discover/movie"
    params = {
        "api_key": TMDB_API_KEY,
        "with_genres": genre_id,
        "sort_by": "popularity.desc",
        "vote_count.gte": 100,
        "vote_average.gte": 6,
        "page": page,
        "language": "fr-FR"
    }
    response = requests.get(url, params=params)
    data = response.json()
    films = data.get("results", [])

    if exclus:
        films = [f for f in films if f["id"] not in exclus]

    if not films:
        return None

    return random.choice(films)

@bot.tree.command(name="film", description="Suggère un film aléatoire selon le genre choisi")
@app_commands.describe(genre="Le genre de film souhaité")
@app_commands.choices(genre=[
    app_commands.Choice(name="Action", value="action"),
    app_commands.Choice(name="Aventure", value="aventure"),
    app_commands.Choice(name="Animation", value="animation"),
    app_commands.Choice(name="Comédie", value="comédie"),
    app_commands.Choice(name="Crime", value="crime"),
    app_commands.Choice(name="Documentaire", value="documentaire"),
    app_commands.Choice(name="Drame", value="drame"),
    app_commands.Choice(name="Famille", value="famille"),
    app_commands.Choice(name="Fantastique", value="fantastique"),
    app_commands.Choice(name="Histoire", value="histoire"),
    app_commands.Choice(name="Horreur", value="horreur"),
    app_commands.Choice(name="Musique", value="musique"),
    app_commands.Choice(name="Mystère", value="mystère"),
    app_commands.Choice(name="Romance", value="romance"),
app_commands.Choice(name="Science-fiction", value="science-fiction"),
    app_commands.Choice(name="Thriller", value="thriller"),
    app_commands.Choice(name="Guerre", value="guerre"),
    app_commands.Choice(name="Western", value="western")
])
async def film_slash(interaction: discord.Interaction, genre: app_commands.Choice[str]):
    genre_nom = genre.value
    genre_id = GENRES[genre_nom]
    user_id = str(interaction.user.id)
    deja_vus = historique.get(user_id, [])

    film = get_film_aleatoire(genre_id, exclus=deja_vus)

    if not film:
        await interaction.response.send_message("😕 Aucun film disponible pour ce genre ou tous déjà proposés.", ephemeral=True)
        return

    historique.setdefault(user_id, []).append(film["id"])

    titre = film["title"]
    description = film.get("overview", "Pas de description.")
    image_url = f"https://image.tmdb.org/t/p/w500{film['poster_path']}" if film.get("poster_path") else None
    note = film.get("vote_average", "N/A")
    annee = film.get("release_date", "N/A")[:4]

    embed = discord.Embed(
        title=titre,
        description=description,
        color=discord.Color.purple()
    )
    if image_url:
        embed.set_thumbnail(url=image_url)
    embed.add_field(name="📅 Année", value=annee, inline=True)
    embed.add_field(name="⭐ Avis", value=f"{note}/10", inline=True)
    embed.set_footer(text=f"Genre : {genre_nom.capitalize()}")

    await interaction.response.send_message(embed=embed)

# --- Commande traditionnelle (gardée pour compatibilité) ---

@bot.command()
async def film(ctx, *, arg):
    if "genre:" not in arg:
        await ctx.send("❗ Utilise la commande comme ceci : `!film genre:action`")
        return

    genre_nom = arg.split("genre:")[1].strip().lower()
    if genre_nom not in GENRES:
        await ctx.send(f"❌ Genre inconnu. Genres valides : {', '.join(GENRES.keys())}")
        return

    genre_id = GENRES[genre_nom]
    user_id = str(ctx.author.id)
    deja_vus = historique.get(user_id, [])

    film = get_film_aleatoire(genre_id, exclus=deja_vus)

    if not film:
        await ctx.send("😕 Aucun film disponible pour ce genre ou tous déjà proposés.")
        return

    historique.setdefault(user_id, []).append(film["id"])

    titre = film["title"]
    description = film.get("overview", "Pas de description.")
    image_url = f"https://image.tmdb.org/t/p/w500{film['poster_path']}" if film.get("poster_path") else None
    note = film.get("vote_average", "N/A")
    annee = film.get("release_date", "N/A")[:4]

    embed = discord.Embed(
        title=titre,
        description=description,
        color=discord.Color.purple()
    )
    if image_url:
        embed.set_thumbnail(url=image_url)
    embed.add_field(name="📅 Année", value=annee, inline=True)
    embed.add_field(name="⭐ Avis", value=f"{note}/10", inline=True)
    embed.set_footer(text=f"Genre : {genre_nom.capitalize()}")

    await ctx.send(embed=embed)

# Configuration
TOKEN = os.environ['Token_bot']  # Remplacez par votre token
CHANNEL_ID = 1398670795684970647  # Remplacez par l'ID du canal (nombre, pas string)

async def get_winning_movie(channel):
  """Trouve le film gagnant du dernier sondage"""
  try:
      # Récupérer les derniers messages du canal
      messages = []
      async for message in channel.history(limit=50):
          messages.append(message)

      # Trouver le dernier message de sondage (qui contient des réactions)
      last_poll = None
      max_reactions = 0

      for message in messages:
          if message.reactions:
              total_reactions = sum(reaction.count for reaction in message.reactions)

              # Considérer ce message comme un sondage potentiel s'il a plus de réactions
              if total_reactions > max_reactions:
                  max_reactions = total_reactions
                  last_poll = message

      if not last_poll:
          return "Aucun sondage trouvé"

      # Trouver la réaction avec le plus de votes
      winning_reaction = None
      max_votes = 0

      for reaction in last_poll.reactions:
          # Soustraire 1 car le bot compte aussi dans les réactions
          vote_count = reaction.count - 1
          if vote_count > max_votes:
              max_votes = vote_count
              winning_reaction = reaction

      if not winning_reaction:
          return "Aucun vote trouvé"

      # Extraire le nom du film du message original
      message_content = last_poll.content
      lines = message_content.split('\n')

      # Chercher la ligne qui correspond à l'emoji gagnant
      winning_emoji = str(winning_reaction.emoji)

      for line in lines:
          if winning_emoji in line:
              # Extraire le titre du film (supprimer les emojis et nettoyer)
              movie_title = re.sub(r'[📽️🎬🎭🎪🎨🎯🎲🎸🎺🎻🥁🎤🎧🎮🎰🎳🎯🎲🎪🎭🎨🎬📽️]', '', line).strip()
              movie_title = re.sub(r':\w+:', '', movie_title).strip()  # Supprimer les emojis custom :nom:
              return movie_title if movie_title else "Film non identifié"

      return f"Film gagnant ({max_votes} votes)"

  except Exception as error:
      print(f'Erreur lors de la récupération du film gagnant: {error}')
      return "Erreur lors de la récupération du sondage"

async def send_movie_announcement():
  """Envoie le message d'annonce du film"""
  try:
      channel = bot.get_channel(CHANNEL_ID)
      if not channel:
          print('Canal non trouvé')
          return

      winning_movie = await get_winning_movie(channel)

      message = (f"🎬 **FILM DE CE SOIR** 🎬\n\n"
                f"Le film **#{winning_movie}** du dernier sondage commence dans **10 minutes** !\n\n"
                f"🍿 Préparez vos snacks et rejoignez-nous ! 🍿")

      await channel.send(message)
      print(f"Message envoyé: Film gagnant - {winning_movie}")

  except Exception as error:
      print(f'Erreur lors de l\'envoi du message: {error}')

async def schedule_daily_task():
  """Fonction pour programmer l'envoi quotidien"""
  paris_tz = pytz.timezone('Europe/Paris')

  while True:
      now = datetime.now(paris_tz)
      target_time = now.replace(hour=20, minute=50, second=0, microsecond=0)

      # Si l'heure est déjà passée aujourd'hui, programmer pour demain
      if now >= target_time:
          target_time = target_time.replace(day=target_time.day + 1)

      # Calculer le temps d'attente
      wait_seconds = (target_time - now).total_seconds()

      print(f"Prochaine annonce programmée à: {target_time}")
      await asyncio.sleep(wait_seconds)

      # Envoyer le message
      print('Envoi du message programmé à 20:50...')
      await send_movie_announcement()

      # Attendre 61 secondes pour éviter d'envoyer plusieurs fois
      await asyncio.sleep(61)

#@bot.event
#async def on_ready():
#  """Événement déclenché quand le bot est connecté"""
#  print(f'Bot connecté en tant que {bot.user}')
#  print('Programmation active: message quotidien à 20:50 heure de Paris')

  # Démarrer la tâche programmée en arrière-plan
#  bot.loop.create_task(schedule_daily_task())

@bot.command(name='test-film')
async def test_film(ctx):
  """Commande pour tester l'envoi du message manuellement"""
  await send_movie_announcement()
  await ctx.send("Message de test envoyé !")

@bot.command(name='film-gagnant')
async def film_gagnant(ctx):
  """Commande pour voir le film gagnant actuel"""
  winning_movie = await get_winning_movie(ctx.channel)
  await ctx.reply(f"Le film gagnant actuel est: **{winning_movie}**")

@bot.event
async def on_command_error(ctx, error):
  """Gestion des erreurs de commandes"""
  print(f'Erreur de commande: {error}')

# Variables globales pour suivre qui a utilisé des objets spéciaux
ticket_special_utilisateurs = {}
double_vote_utilisateurs = {}

TMDB_API_KEY = os.environ['TMDB_API_KEY']
bot.run(TOKEN)
