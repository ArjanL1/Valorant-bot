import discord
import urllib.parse
from bs4 import BeautifulSoup
import requests
from io import BytesIO
from discord.ext import commands
from discord import Embed, Color
from discord.ui import Button
import os

client = commands.Bot(command_prefix="!", intents=discord.Intents.all())

map_matches = {}

@client.event
async def on_ready():
    print(f'We have logged in as {client.user}')
    
@client.event
async def on_message(message):
    if message.author == client.user:
        return
    
    if message.content.startswith('!history'):
        command = message.content.split(' ')
        if len(command) < 2:
            await message.channel.send('Invalid command! Usage: !History <username#id>')
            return
        
        username_id = " ".join(command[1:]).split('#')
        if len(username_id) != 2:
            await message.channel.send('Invalid command! Usage: !History <username#id>')
            return
        
        username = username_id[0].strip()
        player_id = username_id[1].strip()
        api_url = f'https://api.henrikdev.xyz/valorant/v3/matches/na/{username}/{player_id}?filter=competitive'
        
        try:
            response = requests.get(api_url)
            response.raise_for_status()
            data = response.json()
            map_matches.clear()
            for match in data['data']:
                mode = match['metadata']['mode']
                if mode.lower() != 'competitive':
                    continue
                map_name = match['metadata']['map']
                match_id = match['metadata']['matchid']
                if map_name in map_matches:
                    suffix = 2
                    while f"{map_name} ({suffix})" in map_matches:
                        suffix += 1
                    map_name = f"{map_name} ({suffix})"
                map_matches[map_name] = match_id
            if len(map_matches) == 0:
                await message.channel.send("No competitive matches found for the specified user.")
                return
            
            match_ids, mmr_changes = get_mmrinfo(username, player_id)
            if len(match_ids) == 0:
                await message.channel.send("No MMR changes found for the specified user.")
                return
            
            for map_name, match_id in map_matches.items():
                print(match_id)
                api_url = f"https://api.henrikdev.xyz/valorant/v2/match/{match_id}"
                response = requests.get(api_url)
                if response.status_code == 200:
                    match_data = response.json()['data']
                    game_length = match_data['metadata']['game_length']
                    rounds_played = match_data['metadata']['rounds_played']
                    players = match_data['players']['all_players']
                    specified_player = None
                    for player in players:
                        name = player['name']
                        if name.lower() == username.lower():
                            specified_player = player
                            break
                        
                    blue_players = []
                    red_players = []
                    
                    if specified_player:
                        team = specified_player['team']
                        if team == "Blue":
                            blue_players.append(specified_player)
                        elif team == "Red":
                            red_players.append(specified_player)
                    for player in players:
                        if player != specified_player:
                            team = player['team']
                            if team == "Blue":
                                blue_players.append(player)
                            elif team == "Red":
                                red_players.append(player)
                    field_value = f"```ansi\n\033[37mMap: {map_name}\nMode: Competitive\nGame Length: {game_length // 60} minutes\nRounds played: {str(rounds_played)}"
                    if match_id in match_ids:
                        index = match_ids.index(match_id)
                        mmr_change_symbol = mmr_changes[index]
                        if mmr_change_symbol == "Win":
                            outcome_color = "\033[32m"
                        elif mmr_change_symbol == "Loss":
                            outcome_color = "\033[31m"
                        else:
                            outcome_color = ""
                        field_value += f"\nOutcome: {outcome_color}{mmr_change_symbol}"
                    field_value += "```"

                    embed = Embed(title="Match Information", color=Color.green() if mmr_change_symbol == "Win" else Color.red())
                    embed.add_field(name="Match Details", value=field_value, inline=False)
                        
                    def format_player_info(player, specified_player=None):
                        name = player['name']
                        character = player['character']
                        kills = player['stats']['kills']
                        deaths = player['stats']['deaths']
                        assists = player['stats']['assists']
                        kd_ratio = (kills / deaths)
                        headshots = player['stats'].get('headshots', 0)
                        bodyshots = player['stats'].get('bodyshots', 0)
                        legshots = player['stats'].get('legshots', 0)
                        if headshots + bodyshots + legshots > 0:
                            headshot_rate = headshots / (headshots + bodyshots + legshots)
                            bodyshot_rate = bodyshots / (headshots + bodyshots + legshots)
                            legshot_rate = legshots / (headshots + bodyshots + legshots)
                        else:
                            headshot_rate = 0
                            bodyshot_rate = 0
                            legshot_rate = 0
                        if player == specified_player:
                            return f"```ansi\n\033[37mKDA: {kd_ratio:.1f}\nHeadshot Rate: {headshot_rate:.1%}\nBodyshot Rate: {bodyshot_rate:.1%}\nLegshot Rate: {legshot_rate:.1%}\n```"
                        else:
                            team_color = "```ansi\n\033[34m" if player['team'] == "Blue" else "```ansi\n\033[31m"
                            return f"{team_color}{character}|{name}|{kills}/{deaths}/{assists}\n```"
                        
                    blue_team_info = "\n".join(format_player_info(player) if player != specified_player else f"**{format_player_info(player)}**" for player in blue_players)
                    red_team_info = "\n".join(format_player_info(player) if player != specified_player else f"**{format_player_info(player)}**" for player in red_players)
                    embed.add_field(name="Blue Team", value=blue_team_info, inline=True)
                    embed.add_field(name="Red Team", value=red_team_info, inline=True)
                    
                    if specified_player:
                        specified_player_name = specified_player['name'].capitalize()
                        specified_player_info = format_player_info(specified_player, specified_player)
                        embed.add_field(name=f"{specified_player_name}'s Match Stats", value=specified_player_info, inline=False)
                        
                    await message.channel.send(embed=embed)
                    
        except requests.exceptions.HTTPError:
            await message.channel.send(f'An error occurred')

        username = username_id[0].strip()
        player_id = username_id[1].strip()
        api_url = f'https://api.henrikdev.xyz/valorant/v3/matches/na/{username}/{player_id}?filter=competitive'
        print(api_url)
        try:
            response = requests.get(api_url)
            if response.status_code == 200:
                data = response.json()
                if 'data' in data and data['data']:
                    matches = data['data']
                    match_stats = []

                    for match in matches:
                        print("Processing match:", match.get('metadata', {}).get('matchid'))
                        metadata = match.get('metadata', {})
                        players = match.get('players', {}).get('all_players', [])
                        
                        for player in players:
                            if player['name'].lower() == username.lower() and player['tag'].lower() == player_id.lower():
                                print("Matched player found:", player['name'])
                                stats = player.get('stats', {})
                                rounds_played = metadata.get('rounds_played', 0)
                                damage_made = player.get('damage_made', 0)
                                bodyshots = stats.get('bodyshots', 0)
                                headshots = stats.get('headshots', 0)
                                legshots = stats.get('legshots', 0)
                                kills = stats.get('kills', 0)
                                deaths = stats.get('deaths', 0)
                                assists = stats.get('assists', 0)

                                adr = damage_made / rounds_played if rounds_played > 0 else 0
                                total_shots = bodyshots + headshots + legshots
                                headshot_percentage = (headshots / total_shots * 100) if total_shots else 0
                                legshot_percentage = (legshots / total_shots * 100) if total_shots else 0
                                bodyshot_percentage = (bodyshots / total_shots * 100) if total_shots else 0
                                kd_ratio = kills / deaths if deaths else kills

                                match_stats.append({
                                    'damage_made': damage_made,
                                    'rounds_played': rounds_played,
                                    'adr': adr,
                                    'headshot_percentage': headshot_percentage,
                                    'legshot_percentage': legshot_percentage,
                                    'bodyshot_percentage': bodyshot_percentage,
                                    'kd_ratio': kd_ratio
                                })
                                print("Added stats:", match_stats[-1])
                                break
                    if len(match_stats) > 0:
                        total_matches = len(match_stats)
                        total_damage_made = sum(stat['damage_made'] for stat in match_stats)
                        total_rounds_played = sum(stat['rounds_played'] for stat in match_stats)
                        avg_adr = total_damage_made // total_rounds_played
                        avg_headshot_percentage = sum(stat['headshot_percentage'] for stat in match_stats) // total_matches
                        avg_legshot_percentage = sum(stat['legshot_percentage'] for stat in match_stats) // total_matches
                        avg_bodyshot_percentage = sum(stat['bodyshot_percentage'] for stat in match_stats) // total_matches
                        avg_kd_ratio = sum(stat['kd_ratio'] for stat in match_stats) // total_matches
                        
                        ansi_format = "```ansi\n\033[37mKDA: {kd_ratio:.1f}\nHeadshot Rate: {headshot_rate:.1%}\nBodyshot Rate: {bodyshot_rate:.1%}\nLegshot Rate: {legshot_rate:.1%}\nADR: {adr}\n```"
                        username=username.title()
                        stats_footer = ansi_format.format(kd_ratio=avg_kd_ratio, headshot_rate=avg_headshot_percentage/100, bodyshot_rate=avg_bodyshot_percentage/100, legshot_rate=avg_legshot_percentage/100, adr=avg_adr)
                        embed = discord.Embed(title=f"{username}'s Overall Stats", description=stats_footer, color=discord.Color.fuchsia())
                        await message.channel.send(embed=embed)
                    else:
                        await message.channel.send(f"No competitive matches found for {username} ({player_id}).")
            else:
                await message.channel.send('Error occurred while fetching data from the API.')
        except Exception as e:
            await message.channel.send(f'An error occurred: {str(e)}')
            
def get_mmrinfo(username, player_id):
    url = f"https://api.henrikdev.xyz/valorant/v1/mmr-history/na/{username}/{player_id}"
    
    match_ids = []
    mmr_changes = []
    
    try:
        response = requests.get(url)
        data = response.json()
        if response.status_code == 200:
            for match in data['data']:
                match_id = match['match_id']
                mmr_change = match['mmr_change_to_last_game']
                match_ids.append(match_id)
                mmr_changes.append("Win" if mmr_change > 0 else "Loss")
                
            win_count = mmr_changes.count('Win')
            loss_count = mmr_changes.count('Loss')
            win_rate = (win_count / (win_count + loss_count)) * 100
            win_rate = round(win_rate, 2)

        else:
            print("Error")
            
    except Exception as e:
        print("Error")
        
    return match_ids, mmr_changes



client.run('PUT DISCORD TOKEN')
