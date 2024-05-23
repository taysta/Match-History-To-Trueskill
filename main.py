import argparse
import requests
from trueskill import Rating, rate
from prettytable import PrettyTable
from datetime import datetime, timedelta
from dotenv import load_dotenv
import pytz
import os
import json

# Command-line arguments parsing
parser = argparse.ArgumentParser(description='Process some integers.')
parser.add_argument('--domain', type=str, help='API domain')
parser.add_argument('--server_id', type=str, help='Server ID')
parser.add_argument('--date_start', type=str, help='Start date in timestamp')
parser.add_argument('--timezone', type=str, help='Timezone')
parser.add_argument('--min_games', type=int, help='Minimum games required')
parser.add_argument('--last_days_threshold', type=int, help='Last days threshold')
parser.add_argument('--min_games_last_days', type=int, help='Minimum games in last days')
parser.add_argument('--discard_ties', action='store_true', help='Discard ties')
parser.add_argument('--decay_enabled', action='store_true', help='Enable sigma decay')
parser.add_argument('--decay_amount', type=float, help='Decay amount')
parser.add_argument('--grace_days', type=int, help='Grace days for decay')
parser.add_argument('--max_decay_proportion', type=float, help='Max decay proportion')
parser.add_argument('--ts_default_sigma', type=float, help='Default sigma for TrueSkill')
parser.add_argument('--ts_default_mu', type=float, help='Default mu for TrueSkill')
parser.add_argument('--verbose_output', action='store_true', help='Enable verbose output')
parser.add_argument('--top_x', type=int, default=0, help='Show top X players (0 for all)')
parser.add_argument('--write_txt', action='store_true', help='Write output to text file')
parser.add_argument('--write_csv', action='store_true', help='Write output to CSV file')

args = parser.parse_args()

# Load environment variables from .env file
load_dotenv()

# Inputs (override with command-line arguments if provided)
domain = args.domain or os.getenv("DOMAIN")
server_id = args.server_id or os.getenv("SERVER_ID")
time = args.date_start or os.getenv("DATE_START")

# Timezone
timezone_in = args.timezone or os.getenv("TIMEZONE")
timezone = pytz.timezone(timezone_in)

# Alias mappings
user_aliases = json.loads(os.getenv("ALIASED_PLAYERS"))

# Playtime filtering
min_games_required = args.min_games or int(os.getenv("MINIMUM_GAMES_REQUIRED"))

# Activity filtering
last_days_threshold = args.last_days_threshold or int(os.getenv("LAST_DAYS_THRESHOLD"))
min_games_last_days = args.min_games_last_days or int(os.getenv("MINIMUM_GAMES_LAST_DAYS"))

# Top X players filtering
top_x = args.top_x or int(os.getenv("TOP_X_CUTOFF"))

# Discard ties
discard_ties = args.discard_ties or os.getenv("DISCARD_TIES") == 'True'

# Sigma decay
decay_enabled = args.decay_enabled or os.getenv("DECAY_ENABLED") == 'True'
decay_amount = args.decay_amount or float(os.getenv("DECAY_AMOUNT"))
grace_days = args.grace_days or int(os.getenv("DECAY_GRACE_DAYS"))
max_decay_proportion = args.max_decay_proportion or float(os.getenv("MAX_DECAY_PROPORTION"))

# Trueskill
default_sigma = args.ts_default_sigma or float(os.getenv("TS_DEFAULT_SIGMA"))
default_mu = args.ts_default_mu or float(os.getenv("TS_DEFAULT_MU"))

# Verbosity
verbose_output = args.verbose_output or os.getenv("VERBOSE_OUTPUT") == 'True'

# File writing settings
write_txt = args.write_txt or os.getenv("WRITE_TXT") == 'True'
write_csv = args.write_csv or os.getenv("WRITE_CSV") == 'True'

# Counter for games used
games_used_count = 0

# Construct the URL from the input variables
url = f"{domain}/api/server/{server_id}/games/{time}"

# Initialize a dictionary to store player ratings and games played
player_ratings = {}


# Function to fetch game data from the API
def fetch_game_data(in_url):
    response = requests.get(in_url)
    if response.status_code == 200:
        return response.json()
    else:
        raise Exception(f"Failed to fetch data: {response.status_code}")


# Function to get the primary ID for a user
def get_primary_id(user_id):
    for primary_name, aliases in user_aliases.items():
        if user_id in aliases:
            return primary_name
    return user_id


# Function to get the display name for a user
def get_display_name(in_primary_id):
    return player_ratings[in_primary_id]['name']


# Function to get all associated IDs for a primary ID
def get_associated_ids(in_primary_id):
    if in_primary_id in user_aliases:
        return ",".join(user_aliases[in_primary_id])
    return in_primary_id


# Function to apply sigma decay
def apply_sigma_decay(player, inactivity_days):
    if decay_enabled and inactivity_days > grace_days:
        max_sigma_increase = default_sigma * max_decay_proportion - player['rating'].sigma
        if max_sigma_increase > 0:
            total_decay = min(decay_amount * inactivity_days, max_sigma_increase)
            new_sigma = player['rating'].sigma + total_decay
            player['rating'] = Rating(mu=player['rating'].mu, sigma=new_sigma)


# Function to update last played date for primary ID based on activity of all associated IDs
def update_last_played(in_primary_id, current_date):
    player = player_ratings[in_primary_id]
    if current_date > player['last_played']:
        player['last_played'] = current_date


# Function to process a single game
def process_game(in_game, in_played_dates):
    global games_used_count
    current_date = datetime.fromtimestamp(in_game['completionTimestamp'] / 1000, timezone).date()

    # Track the dates on which games were played
    if current_date not in in_played_dates:
        in_played_dates[current_date] = set()
    for player in in_game['players']:
        in_played_dates[current_date].add(player['user']['id'])

    winning_team = in_game['winningTeam']
    if discard_ties and winning_team == 0:
        return  # Discard the game if there's no winning team and discard_ties is True

    games_used_count += 1

    team1 = []
    team2 = []
    team1_ids = []
    team2_ids = []

    for player in in_game['players']:
        user_id = str(player['user']['id'])
        user_name = player['user']['name']
        in_primary_id = get_primary_id(user_id)
        pick_order = player['pickOrder'] if player['pickOrder'] is not None else 0

        if in_primary_id not in player_ratings:
            player_ratings[in_primary_id] = {
                'name': user_name,
                'rating': Rating(mu=default_mu, sigma=default_sigma),
                'games_played': 0,
                'wins': 0,
                'losses': 0,
                'last_played': current_date,
                'secondary_ids': set(),
                'total_pick_order': 0,
                'pick_order_count': 0,
                'avg_pick_order': 0.0,
                'recent_games': 0
            }

        player_ratings[in_primary_id]['games_played'] += 1

        # Track recent games
        if current_date >= datetime.now(timezone).date() - timedelta(days=last_days_threshold):
            player_ratings[in_primary_id]['recent_games'] += 1

        # Only count pick order if the player is not the captain
        if player['captain'] == 0:
            player_ratings[in_primary_id]['total_pick_order'] += pick_order
            player_ratings[in_primary_id]['pick_order_count'] += 1
            player_ratings[in_primary_id]['avg_pick_order'] = (player_ratings[in_primary_id]['total_pick_order'] /
                                                               player_ratings[in_primary_id]['pick_order_count'])

        player_ratings[in_primary_id]['secondary_ids'].add(user_id)
        update_last_played(in_primary_id, current_date)

        if player['team'] == 1:
            team1.append(player_ratings[in_primary_id]['rating'])
            team1_ids.append(in_primary_id)
        else:
            team2.append(player_ratings[in_primary_id]['rating'])
            team2_ids.append(in_primary_id)

    # Update ratings based on match result
    if winning_team == 1:
        new_team1_ratings, new_team2_ratings = rate([team1, team2])
        for user_id in team1_ids:
            player_ratings[user_id]['wins'] += 1
        for user_id in team2_ids:
            player_ratings[user_id]['losses'] += 1
    else:
        new_team2_ratings, new_team1_ratings = rate([team2, team1])
        for user_id in team2_ids:
            player_ratings[user_id]['wins'] += 1
        for user_id in team1_ids:
            player_ratings[user_id]['losses'] += 1

    # Save updated ratings back to the dictionary
    for i, user_id in enumerate(team1_ids):
        player_ratings[user_id]['rating'] = new_team1_ratings[i]
    for i, user_id in enumerate(team2_ids):
        player_ratings[user_id]['rating'] = new_team2_ratings[i]


# Function to sort and display player ratings in a table
def display_ratings(in_server_id, in_start_date_str, in_end_date_str, in_min_games_required, in_discard_ties, in_url,
                    in_decay_enabled, in_top_x):
    current_date = datetime.now(timezone).date()
    start_date_threshold = current_date - timedelta(days=last_days_threshold)

    # Step 1: Filter out players with less than the minimum required games played
    filtered_players = {user_id: data for user_id, data in player_ratings.items() if
                        data['games_played'] >= in_min_games_required}

    # Step 2: Filter based on last_days_threshold
    if last_days_threshold > 0:
        filtered_players = {user_id: data for user_id, data in filtered_players.items()
                            if data['last_played'] >= start_date_threshold}

    # Step 3: Filter based on min_games_last_days
    if min_games_last_days > 0:
        filtered_players = {user_id: data for user_id, data in filtered_players.items()
                            if data['recent_games'] >= min_games_last_days}

    # Sort players by their conservative TrueSkill rating (mu - 3 * sigma)
    sorted_players = sorted(filtered_players.items(), key=lambda x: x[1]['rating'].mu - 3 * x[1]['rating'].sigma,
                            reverse=True)

    # Calculate the number of players below the cutoff
    cutoff_count = max(0, len(sorted_players) - in_top_x) if in_top_x > 0 else 0

    # Limit the number of players to display if in_top_x is greater than 0
    if in_top_x > 0:
        sorted_players = sorted_players[:in_top_x]

    table = PrettyTable()

    if verbose_output:
        table.field_names = ["Rank", "Name", "Trueskill Rating (μ - 3*σ)", "μ (mu)", "σ (sigma)", "Games Played",
                             "Win/Loss", "Last Played", "Avg Pick Order", "Discord ID/s"]
    else:
        table.field_names = ["Rank", "Name", "Trueskill Rating (μ - 3*σ)", "μ (mu)", "σ (sigma)", "Games Played",
                             "Win/Loss", "Last Played", "Avg Pick Order"]

    rows = []

    for rank, player in enumerate(sorted_players, start=1):
        in_primary_id = player[0]
        rating = player[1]['rating']
        games_played = player[1]['games_played']
        wins = player[1]['wins']
        losses = player[1]['losses']
        last_played = player[1]['last_played'].strftime('%Y-%m-%d')
        avg_pick_order = player[1]['avg_pick_order']
        display_name = get_display_name(in_primary_id)

        if verbose_output:
            associated_ids = get_associated_ids(in_primary_id)
            row = [
                rank,
                display_name,
                f"{rating.mu - 3 * rating.sigma:.2f}",  # Conservative rating estimate
                f"{rating.mu:.2f}",
                f"{rating.sigma:.2f}",
                games_played,
                f"{wins}/{losses}",
                last_played,
                f"{avg_pick_order:.2f}",
                associated_ids
            ]
        else:
            row = [
                rank,
                display_name,
                f"{rating.mu - 3 * rating.sigma:.2f}",  # Conservative rating estimate
                f"{rating.mu:.2f}",
                f"{rating.sigma:.2f}",
                games_played,
                f"{wins}/{losses}",
                last_played,
                f"{avg_pick_order:.2f}"
            ]
        rows.append(row)
        table.add_row(row)

    decay_settings = ""
    if in_decay_enabled:
        decay_settings = (f"decay_amount={decay_amount}, "
                          f"grace_days={grace_days}, "
                          f"max_decay_proportion={max_decay_proportion}")

    # Print the output to console
    if verbose_output:
        print(f"Input URL: {in_url}")
        print(f"Server ID: {in_server_id}")

    print(f"Games period: From {in_start_date_str} to {in_end_date_str}")
    print(f"Games used: {games_used_count}")
    print(table)
    print(f"Sigma decay: {decay_settings if in_decay_enabled else 'Disabled'}")
    print(f"Minimum games required: {in_min_games_required} ({len(filtered_players)} players filtered)")

    if in_top_x > 0:
        print(f"Showing top {in_top_x} players ({cutoff_count} cutoff)")

    print(f"Ties discarded: {in_discard_ties}")
    print(f"Aliased player/s: {', '.join(user_aliases.keys())}")

    # Save the table to a text file if enabled
    if write_txt:
        with open("player_ratings.txt", "w") as text_file:
            if verbose_output:
                text_file.write(f"Input URL: {in_url}\n")
                text_file.write(f"Server ID: {in_server_id}\n")
            text_file.write(f"Games period: From {in_start_date_str} to {in_end_date_str}\n")
            text_file.write(f"Games used: {games_used_count}\n")
            text_file.write(str(table))
            text_file.write(f"\nRating decay: {decay_settings if in_decay_enabled else 'Disabled'}\n")
            text_file.write(f"Minimum games required: {in_min_games_required} "
                            f"({len(filtered_players)} players filtered)\n")
            if in_top_x > 0:
                text_file.write(f"Showing top {in_top_x} players ({cutoff_count} cutoff)\n")
            text_file.write(f"Ties discarded: {in_discard_ties}\n")
            text_file.write(f"Aliased player/s: {', '.join(user_aliases.keys())}\n")

    # Save the table to a CSV file if enabled
    if write_csv:
        with open("player_ratings.csv", "w") as csv_file:
            if verbose_output:
                csv_file.write("Rank,Name,Trueskill Rating (μ - 3*σ),μ (mu),σ (sigma),Games Played,"
                               "Win/Loss,Last Played,Avg Pick Order,Discord ID/s\n")
            else:
                csv_file.write("Rank,Name,Trueskill Rating (μ - 3*σ),μ (mu),σ (sigma),Games Played,"
                               "Win/Loss,Last Played,Avg Pick Order\n")
            for row in rows:
                csv_file.write(",".join(map(str, row)) + "\n")


def run():
    # Convert the time variable to a human-readable date string
    start_date_str = datetime.fromtimestamp(int(time) / 1000, timezone).strftime('%Y-%m-%d')
    end_date_str = datetime.now(timezone).strftime('%Y-%m-%d %I:%M %p %Z')

    games = fetch_game_data(url)

    # Track dates when games are played
    played_dates = {}

    for game in games:
        process_game(game, played_dates)

    # Apply sigma decay for players on consecutive days they did not play, but games were played
    previous_date = None
    for date in sorted(played_dates.keys()):
        participants = played_dates[date]
        if previous_date:
            for player_id in player_ratings:
                primary_id = get_primary_id(player_id)
                if primary_id not in participants:
                    days_inactive = (date - player_ratings[primary_id]['last_played']).days
                    if days_inactive > grace_days:
                        apply_sigma_decay(player_ratings[primary_id], days_inactive)
        previous_date = date

    display_ratings(
        server_id, start_date_str, end_date_str, min_games_required, discard_ties, url, decay_enabled, top_x)


# Run the program
run()
