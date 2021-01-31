import os
from wow_groups import get_groups
import random
import logging
import time
import discord
from discord.ext import commands
from discord.utils import get

poll = {}
bot = commands.Bot(command_prefix="!", intents=discord.Intents().default())
bot_user_name = ''
GROUP_SIZE = 5
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD = os.getenv("GUILD")
CHANNEL = os.getenv("CHANNEL")
MAX_DURATION_IN_SEC = 3600
vote_opening = [
    "1.. 2.. 3.. Votez pour vôtre rôle en cliquant sur l'icône!"
    "Ouverture du vôte pour vôtre rôle en donjon",
    "Un jour, un rôle, quelle est vôtre humeur du moment?",
    "Que de monde! Essayons de classer les groupes",
    "Hop hop hop, on click et on part en donjon !",
    "Laissez-moi vous aider à préparer vos groupes",
    "Alors comme ça on a besoin d'un petit coup de main pour lancer les groupes ?",
    "Les groupes sont en formation, cliquez sur les icones ci-dessous pour vous inscrire"
]


# Logging
logger = logging.getLogger()
handler = logging.StreamHandler()
formatter = logging.Formatter(
        '%(asctime)s %(name)-12s %(levelname)-8s %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)
logger.setLevel(logging.INFO)


"""
Converts the dictionnary of Discord players emojis
to the input array used by the group computing program
"""
def format_players_for_group_lib():
    global poll
    
    logger.debug(f'---- format_players_for_group_lib ----\nbot user name: {bot_user_name}')

    players = poll['players']
    result = []
    for player_id in players:
        player = {}
        player['wishes'] = {}
        username = ''
        if 'dps_low' in players[player_id]:
            username = players[player_id]['dps_low']
            player['wishes']['dps'] = 2
        if 'dps_high' in players[player_id]:
            username = players[player_id]['dps_high']
            player['wishes']['dps'] = 5
        if 'heal_low' in players[player_id]:
            username = players[player_id]['heal_low']
            player['wishes']['heal'] = 2
        if 'heal_high' in players[player_id]:
            username = players[player_id]['heal_high']
            player['wishes']['heal'] = 5
        if 'tank_low' in players[player_id]:
            username = players[player_id]['tank_low']
            player['wishes']['tank'] = 2
        if 'tank_high' in players[player_id]:
            username = players[player_id]['tank_high']
            player['wishes']['tank'] = 5
        player['name'] = username
        if username != bot_user_name:
            result.append(player)
    logger.info(f'Player array before computing: {result}')
    return result


"""
Connect the bot to the guild (from GUILD environment variable)
and fetch the bot user name in the guild
"""
@bot.event
async def on_ready():
    global bot_user_name
    logger.debug(f'---- on_ready ----')
    for guild in bot.guilds:
        logger.debug(f'Guild objects: {guild}')
        if guild.name == GUILD:
            bot_user_name = bot.user.name
            logger.info(
                f'{bot.user} est connecté à la guilde:\n'
                f'{guild.name}(id: {guild.id})')
            break


"""
get all emojis we need from the guild
and store them in a local dict
"""
async def fetch_emojis(ctx):
    global poll
    poll['emoji'] = {}
    poll['emoji']["dps_low"] = get(ctx.guild.emojis, name='dps_low')
    poll['emoji']["dps_high"] = get(ctx.guild.emojis, name='dps_high')
    poll['emoji']["heal_low"] = get(ctx.guild.emojis, name='heal_low')
    poll['emoji']["heal_high"] = get(ctx.guild.emojis, name='heal_high')
    poll['emoji']["tank_low"] = get(ctx.guild.emojis, name='tank_low')
    poll['emoji']["tank_high"] = get(ctx.guild.emojis, name='tank_high')
    poll['emoji']["stop"] = get(ctx.guild.emojis, name='stop')
    poll['emoji']["done"] = get(ctx.guild.emojis, name='done')
    logger.debug(f'Emoji gathered')


"""
Poll is ongoing: is not finished and not expired
"""
def is_poll_ongoing():
    return poll['message'] != None and ( time.time() - poll['start'] < MAX_DURATION_IN_SEC )


"""
Starts a new group poll
"""
@bot.command(name='group', brief="Start group poll.")
async def group(ctx):
    global poll

    logger.debug(f'---- group ----\nctx:{ctx}\nchannel: {ctx.message.channel}')

    if ctx.channel.name != CHANNEL:
        logger.warning(f'invalid channel for bot command ({ctx.channel.name})')
        return

    if is_poll_ongoing():
        logger.info(f'new poll requested and current poll ongoing')
        await ctx.send("Un vote est déjà en cours sur les rôle dans le groupe.")
    else:
        # create new poll
        poll['players'] = {}
        poll['context'] = ctx
        poll['start'] = time.time()
        poll['message'] = await ctx.send(f"Poll: {random.choice(vote_opening)} - {ctx.author.name.capitalize()}")
        logger.info(f'Creating new poll with message_id: {poll["message"].id}')
        # Display all required emojis in the message
        await fetch_emojis(ctx)
        for emo in poll['emoji']:
            if emo == 'done':
                continue
            await poll['message'].add_reaction(poll['emoji'][emo])


"""
Return True if the reaction should be added to the internal array,
False otherwise
"""
def is_reaction_valid(payload, test_for_bot = False):

    # ignore the bot itself
    if test_for_bot and payload.member.name == bot_user_name:
        logger.debug('Ignoring bot')
        return False
   
    # No vote in action
    if not is_poll_ongoing():
        logger.debug('No ongoing vote')
        return False

    # Message is not the ongoing poll
    if poll['message'].id != payload.message_id:
        logger.debug(f'Message reaction is not current poll')
        return False

     # Emoji not in list
    if payload.emoji.name not in poll['emoji']:
        logger.debug(f'Message reaction is not in accepted list ({payload.emoji.name})')
        return False
    
    return True


"""
Display poll results 
"""
async def display_poll_result():
    global poll

    await poll['message'].add_reaction(poll['emoji']['done'])
    if len(poll['solution']) == 0:
        await poll['context'].send(f"Je suis désolé, je n'ai pas trouvé de solution.")
    else:
        await poll['context'].send(f"Voici ma proposition:\n\n{format_group(poll['solution'])}")


"""
Get reaction on the poll message and update internal array representation
of who wants to do what.
Adding stop emoji stops the poll and sends results
"""
@bot.event
async def on_raw_reaction_add(payload):
    global poll

    logger.debug(f'---- on_raw_reaction_add ----\npayload:{payload}')
    if not is_reaction_valid(payload, test_for_bot = True):
        return
    logger.info(f'Add Reaction | User: {payload.member.name} | User id: {payload.user_id} | Message_id: {payload.message_id} | Reaction: {payload.emoji}')

    # Add player to the map if it doesn't exists
    if payload.user_id not in poll['players']:
        poll['players'][payload.user_id] = {}

    logger.warn(f'stop:{payload.emoji.name.startswith("stop")}')

    # Update internal player map
    if payload.emoji.name in poll['emoji'] and not payload.emoji.name.startswith("stop"):
        poll['players'][payload.user_id][payload.emoji.name] = payload.member.name

    # Stop the poll if stop emoji is clicked by someone else than the bot
    elif payload.emoji.name.startswith("stop") and payload.member.name != bot_user_name:
        logger.info(f'poll stopped by {payload.member.name}')
        poll['solution'] = get_groups(format_players_for_group_lib(), GROUP_SIZE)
        await display_poll_result()
        poll['message'] = None

    # Clean player array
    # Useful if the first player click is not a role emoji, but still an emoji of the authorized array
    if len(poll['players'][payload.user_id]) == 0:
         del poll['players'][payload.user_id]

    logger.debug(poll['players'])


"""
Removes the player's choice from the internal 
"""
@bot.event
async def on_raw_reaction_remove(payload):
    global bot_user_name
    global poll

    logger.debug(f'---- on_raw_reaction_remove ----\npayload:{payload}')
    if not is_reaction_valid(payload):
        return
    logger.info(f'Remove Reaction | User id: {payload.user_id} | Message_id: {payload.message_id} | Reaction: {payload.emoji}')

    # Clear internal player map only if emoji is allowed and is present
    if ( payload.emoji.name in poll['emoji'] ) and ( payload.emoji.name in poll['players'][payload.user_id] ):
        del poll['players'][payload.user_id][payload.emoji.name]

    # if all roles have been removed from player, let's clean it
    if len(poll['players'][payload.user_id]) == 0:
         del poll['players'][payload.user_id]

    logger.debug(poll['players'])


"""
Cancel any ongoing poll
"""
@bot.command(name='cancel', brief="Cancel any ongoing group poll.")
async def cancel(ctx):
    global poll

    logger.debug(f'---- cancel ----\nctx:{ctx}')
    if ctx.channel.name != CHANNEL:
        logger.warning(f'invalid channel for bot command ({ctx.channel.name})')
        return

    if is_poll_ongoing():
        await poll['message'].add_reaction(poll['emoji']['done'])
        await ctx.send("Le vote en cours est annulé, prêt à en démarrer un nouveau !")
        poll['message'] = None
    else:
        await ctx.send("Pas de vote en cours, je suis prêt à en démarrer un nouveau !")


"""
Format current group solution for proper display in Discord
"""
def format_group(solution):
    str_groups = ''
    for group in solution:               
        # Get results
        str_groups += 'Groupe {group_id}\n'.format(group_id=group['id'])
        for member in group['members']:
            name = member['name'].capitalize()
            str_groups += '    - {member_name}\t{member_role}\n'.format(member_name=name, member_role=member['role'])
        str_groups += '\n'
    return str_groups


"""
Main method execution
"""
if __name__ == "__main__":
    poll['emoji'] = {}
    poll['players'] = {}
    poll['message'] = None
    poll['context'] = None
    poll['solution'] = None
    poll['start'] = time.gmtime(0)
    if TOKEN != None:
        logger.info(f'Discord token is found: {TOKEN[0:4]}...{TOKEN[-4:]}')
    else:
        logger.error(f'No token defined')
    bot.run(TOKEN)