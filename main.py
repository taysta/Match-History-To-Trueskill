import argparse
import requests
from trueskill import Rating, rate
from prettytable import PrettyTable
from datetime import datetime, timedelta
from dotenv import load_dotenv
import pytz
import os
import json
import sys


def handle_error(exception, msg):
    print(f"Error: {msg}")
    print(f"Exception: {str(exception)}")
    sys.exit(1)


class Player:
    def __init__(self, user_id, user_name, default_mu, default_sigma):
        self.user_id = user_id
        self.name = user_name
        self.rating = Rating(mu=default_mu, sigma=default_sigma)
        self.games_played = 0
        self.wins = 0
        self.losses = 0
        self.last_played = None
        self.secondary_ids = set()
        self.total_pick_order = 0
        self.pick_order_count = 0
        self.avg_pick_order = 0.0
        self.recent_games = 0

    def update_pick_order(self, pick_order):
        self.total_pick_order += pick_order
        self.pick_order_count += 1
        self.avg_pick_order = self.total_pick_order / self.pick_order_count

    def add_game(self, is_win, current_date, is_recent_game):
        self.games_played += 1
        if is_win:
            self.wins += 1
        else:
            self.losses += 1
        if self.last_played is None or current_date > self.last_played:
            self.last_played = current_date
        if is_recent_game:
            self.recent_games += 1

    def apply_sigma_decay(self, decay_amount, max_decay_proportion, inactivity_days, default_sigma):
        max_sigma_increase = default_sigma * max_decay_proportion - self.rating.sigma
        if max_sigma_increase > 0:
            total_decay = min(decay_amount * inactivity_days, max_sigma_increase)
            new_sigma = self.rating.sigma + total_decay
            self.rating = Rating(mu=self.rating.mu, sigma=new_sigma)


class GameProcessor:
    def __init__(self, domain, server_id, start_date, timezone, min_games_required, last_days_threshold,
                 min_games_last_days, discard_ties, decay_enabled, decay_amount, grace_days,
                 max_decay_proportion, default_sigma, default_mu, verbose_output, top_x, write_txt, write_csv,
                 json_file):
        self.domain = domain
        self.server_id = server_id
        self.start_date = start_date
        self.timezone = timezone
        self.min_games_required = min_games_required
        self.last_days_threshold = last_days_threshold
        self.min_games_last_days = min_games_last_days
        self.discard_ties = discard_ties
        self.decay_enabled = decay_enabled
        self.decay_amount = decay_amount
        self.grace_days = grace_days
        self.max_decay_proportion = max_decay_proportion
        self.default_sigma = default_sigma
        self.default_mu = default_mu
        self.verbose_output = verbose_output
        self.top_x = top_x
        self.write_txt = write_txt
        self.write_csv = write_csv
        self.json_file = json_file
        self.url = f"{self.domain}/api/server/{self.server_id}/games/{self.start_date}"
        self.player_ratings = {}
        self.primary_ids_cache = {}
        self.games_used_count = 0
        self.user_aliases = {}
        self.filtered_by_min_games = 0
        self.filtered_by_last_days = 0
        self.filtered_by_min_games_last_days = 0

    def fetch_game_data(self):
        try:
            response = requests.get(self.url)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            handle_error(e, f"Failed to fetch data from {self.url}")

    def read_game_data_from_file(self):
        try:
            with open(self.json_file, 'r') as file:
                return json.load(file)
        except Exception as e:
            handle_error(e, f"Failed to read game data from file {self.json_file}")

    def get_primary_id(self, user_id):
        if user_id in self.primary_ids_cache:
            return self.primary_ids_cache[user_id]
        for primary_name, aliases in self.user_aliases.items():
            if user_id in aliases:
                self.primary_ids_cache[user_id] = primary_name
                return primary_name
        self.primary_ids_cache[user_id] = user_id
        return user_id

    def get_player(self, user_id, user_name):
        primary_id = self.get_primary_id(user_id)
        if primary_id not in self.player_ratings:
            self.player_ratings[primary_id] = Player(primary_id, user_name, self.default_mu, self.default_sigma)
        return self.player_ratings[primary_id]

    def process_game(self, game, played_dates):
        current_date = None
        try:
            current_date = datetime.fromtimestamp(game['completionTimestamp'] / 1000, self.timezone).date()
        except Exception as e:
            handle_error(e, f"Failed to convert timestamp for game {game}")

        # Track the dates on which games were played
        if current_date not in played_dates:
            played_dates[current_date] = set()
        try:
            for player in game['players']:
                played_dates[current_date].add(player['user']['id'])
        except KeyError:
            handle_error(KeyError, f"Player ID not found in game data {game}")

        try:
            winning_team = game['winningTeam']
            if self.discard_ties and winning_team == 0:
                return

            self.games_used_count += 1

            team1 = []
            team2 = []
            team1_ids = []
            team2_ids = []

            now_date = datetime.now(self.timezone).date()
            threshold_date = now_date - timedelta(days=self.last_days_threshold)

            for player_data in game['players']:
                user_id = str(player_data['user']['id'])
                user_name = player_data['user']['name']
                player = self.get_player(user_id, user_name)
                pick_order = player_data['pickOrder'] if player_data['pickOrder'] is not None else 0

                is_win = winning_team == player_data['team']
                is_recent_game = current_date >= threshold_date

                player.add_game(is_win, current_date, is_recent_game)

                # Only count pick order if the player is not the captain
                if player_data['captain'] == 0:
                    player.update_pick_order(pick_order)

                player.secondary_ids.add(user_id)

                if player_data['team'] == 1:
                    team1.append(player.rating)
                    team1_ids.append(player.user_id)
                else:
                    team2.append(player.rating)
                    team2_ids.append(player.user_id)

            # Update ratings based on match result
            self.update_ratings(team1, team1_ids, team2, team2_ids, winning_team)
        except KeyError as e:
            handle_error(e, f"Failed to process game {game}")

    def update_ratings(self, team1, team1_ids, team2, team2_ids, winning_team):
        if winning_team == 1:
            new_team1_ratings, new_team2_ratings = rate([team1, team2])
            self.update_team_stats(team1_ids, new_team1_ratings, True)
            self.update_team_stats(team2_ids, new_team2_ratings, False)
        else:
            new_team2_ratings, new_team1_ratings = rate([team2, team1])
            self.update_team_stats(team2_ids, new_team2_ratings, True)
            self.update_team_stats(team1_ids, new_team1_ratings, False)

    def update_team_stats(self, team_ids, new_ratings, is_win):
        for i, user_id in enumerate(team_ids):
            player = self.player_ratings[user_id]
            player.rating = new_ratings[i]
            if is_win:
                player.wins += 1
            else:
                player.losses += 1

    def apply_decay(self, played_dates):
        previous_date = None
        for date in sorted(played_dates.keys()):
            participants = played_dates[date]
            if previous_date:
                for player_id in self.player_ratings:
                    primary_id = self.get_primary_id(player_id)
                    if primary_id not in participants:
                        days_inactive = (date - self.player_ratings[primary_id].last_played).days
                        if days_inactive > self.grace_days:
                            self.player_ratings[primary_id].apply_sigma_decay(self.decay_amount,
                                                                              self.max_decay_proportion, days_inactive,
                                                                              self.default_sigma)
            previous_date = date

    def display_ratings(self, start_date_str, end_date_str, stream=sys.stdout):
        print(f"{end_date_str}")
        current_date = datetime.now(self.timezone).date()
        start_date_threshold = current_date - timedelta(days=self.last_days_threshold)

        # Filter out players with less than the minimum required games played
        initial_player_count = len(self.player_ratings)
        filtered_players = {user_id: data for user_id, data in self.player_ratings.items() if
                            data.games_played >= self.min_games_required}
        self.filtered_by_min_games = initial_player_count - len(filtered_players)

        # Filter based on last_days_threshold
        if self.last_days_threshold > 0:
            initial_filtered_count = len(filtered_players)
            filtered_players = {user_id: data for user_id, data in filtered_players.items()
                                if data.last_played >= start_date_threshold}
            self.filtered_by_last_days = initial_filtered_count - len(filtered_players)

        # Filter based on min_games_last_days
        if self.min_games_last_days > 0:
            initial_filtered_count = len(filtered_players)
            filtered_players = {user_id: data for user_id, data in filtered_players.items()
                                if data.recent_games >= self.min_games_last_days}
            self.filtered_by_min_games_last_days = initial_filtered_count - len(filtered_players)

        # Sort players by their conservative TrueSkill rating (mu - 3 * sigma)
        sorted_players = sorted(filtered_players.items(), key=lambda x: x[1].rating.mu - 3 * x[1].rating.sigma,
                                reverse=True)

        # Calculate the number of players below the cutoff
        cutoff_count = max(0, len(sorted_players) - self.top_x) if self.top_x > 0 else 0

        # Limit the number of players to display if self.top_x is greater than 0
        if self.top_x > 0:
            sorted_players = sorted_players[:self.top_x]

        table = PrettyTable()

        if self.verbose_output:
            table.field_names = ["Rank", "Name", "Trueskill Rating (μ - 3*σ)", "μ (mu)", "σ (sigma)", "Games Played",
                                 "Win/Loss", "Last Played", "Avg Pick Order", "Discord ID/s"]
        else:
            table.field_names = ["Rank", "Name", "Trueskill Rating (μ - 3*σ)", "μ (mu)", "σ (sigma)", "Games Played",
                                 "Win/Loss", "Last Played", "Avg Pick Order"]

        rows = []

        for rank, (user_id, player) in enumerate(sorted_players, start=1):
            rating = player.rating
            games_played = player.games_played
            wins = player.wins
            losses = player.losses
            last_played = player.last_played.strftime('%Y-%m-%d')
            avg_pick_order = player.avg_pick_order
            display_name = player.name

            if self.verbose_output:
                associated_ids = ",".join(player.secondary_ids)
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
        if self.decay_enabled:
            decay_settings = (f"decay_amount={self.decay_amount}, "
                              f"grace_days={self.grace_days}, "
                              f"max_decay_proportion={self.max_decay_proportion}")

        # Print the output to console
        if self.verbose_output:
            print(f"Input URL: {self.url}", file=stream)
            print(f"Server ID: {self.server_id}", file=stream)

        print(f"Games period: From {start_date_str} to {end_date_str}", file=stream)
        print(f"Games used: {self.games_used_count}", file=stream)
        print(table, file=stream)
        print(f"Sigma decay: {decay_settings if self.decay_enabled else 'Disabled'}", file=stream)
        print(f"Minimum games required: {self.min_games_required} ({self.filtered_by_min_games} players filtered)",
              file=stream)
        if self.last_days_threshold > 0:
            print(f"Last days threshold: {self.last_days_threshold} ({self.filtered_by_last_days} players filtered)",
                  file=stream)
        if self.min_games_last_days > 0:
            print(f"Min games in last days threshold: {self.min_games_last_days} "
                  f"({self.filtered_by_min_games_last_days} players filtered)", file=stream)
        if self.top_x > 0:
            print(f"Showing top {self.top_x} players ({cutoff_count} cutoff)", file=stream)

        print(f"Ties discarded: {self.discard_ties}", file=stream)
        print(f"Aliased player/s: {', '.join(self.user_aliases.keys())}", file=stream)

        # Get current timestamp for unique filenames
        timestamp = datetime.now(self.timezone).strftime('%Y%m%d_%H%M%S')

        # Save the text output to a text file if enabled
        if self.write_txt:
            txt_filename = f"out/player_ratings_{timestamp}.txt"
            with open(txt_filename, "w", encoding="utf-8") as text_file:
                if self.verbose_output:
                    text_file.write(f"Input URL: {self.url}\n")
                    text_file.write(f"Server ID: {self.server_id}\n")
                text_file.write(f"Games period: From {start_date_str} to {end_date_str}\n")
                text_file.write(f"Games used: {self.games_used_count}\n")
                text_file.write(str(table))
                text_file.write(f"\nRating decay: {decay_settings if self.decay_enabled else 'Disabled'}\n")
                text_file.write(f"Minimum games required: {self.min_games_required} "
                                f"({self.filtered_by_min_games} players filtered)\n")
                if self.last_days_threshold > 0:
                    text_file.write(f"Last days threshold: {self.last_days_threshold} "
                                    f"({self.filtered_by_last_days} players filtered)\n")
                if self.min_games_last_days > 0:
                    text_file.write(f"Min games in last days threshold: {self.min_games_last_days} "
                                    f"({self.filtered_by_min_games_last_days} players filtered)\n")
                if self.top_x > 0:
                    text_file.write(f"Showing top {self.top_x} players ({cutoff_count} cutoff)\n")
                text_file.write(f"Ties discarded: {self.discard_ties}\n")
                text_file.write(f"Aliased player/s: {', '.join(self.user_aliases.keys())}\n")

        # Save the table to a CSV file if enabled
        if self.write_csv:
            csv_filename = f"out/player_ratings_{timestamp}.csv"
            with open(csv_filename, "w", encoding="utf-8") as csv_file:
                if self.verbose_output:
                    csv_file.write("Rank,Name,Trueskill Rating (μ - 3*σ),μ (mu),σ (sigma),Games Played,"
                                   "Win/Loss,Last Played,Avg Pick Order,Discord ID/s\n")
                else:
                    csv_file.write("Rank,Name,Trueskill Rating (μ - 3*σ),μ (mu),σ (sigma),Games Played,"
                                   "Win/Loss,Last Played,Avg Pick Order\n")
                for row in rows:
                    csv_file.write(",".join(map(str, row)) + "\n")

    def run(self):
        start_date_str = datetime.fromtimestamp(int(self.start_date) / 1000, self.timezone).strftime('%Y-%m-%d')
        end_date_str = datetime.now(self.timezone).strftime('%Y-%m-%d %I:%M %p %Z')

        if self.json_file:
            games = self.read_game_data_from_file()
        else:
            games = self.fetch_game_data()

        played_dates = {}

        for game in games:
            self.process_game(game, played_dates)

        self.apply_decay(played_dates)
        self.display_ratings(start_date_str, end_date_str)


# Main execution
def main():
    parser = argparse.ArgumentParser(description='Process team game match history into TrueSkill data.')
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
    parser.add_argument('--json_file', type=str, help='Path to JSON file containing game data')

    try:
        args = parser.parse_args()
    except Exception as parse_args_exception:
        handle_error(parse_args_exception, "Failed to parse command-line arguments")
        return

    try:
        load_dotenv()
    except Exception as load_dotenv_exception:
        handle_error(load_dotenv_exception, "Failed to load environment variables from .env file")
        return

    try:
        # Inputs (override with command-line arguments if provided)
        domain = args.domain or os.getenv("DOMAIN")
        server_id = args.server_id or os.getenv("SERVER_ID")
        start_date = args.date_start or os.getenv("DATE_START")
        timezone_in = args.timezone or os.getenv("TIMEZONE")
        timezone = pytz.timezone(timezone_in)
        user_aliases = json.loads(os.getenv("ALIASED_PLAYERS"))

        min_games_required = args.min_games or int(os.getenv("MINIMUM_GAMES_REQUIRED"))
        last_days_threshold = args.last_days_threshold or int(os.getenv("LAST_DAYS_THRESHOLD"))
        min_games_last_days = args.min_games_last_days or int(os.getenv("MINIMUM_GAMES_LAST_DAYS"))
        top_x = args.top_x or int(os.getenv("TOP_X_CUTOFF"))

        discard_ties = args.discard_ties or os.getenv("DISCARD_TIES") == 'True'
        decay_enabled = args.decay_enabled or os.getenv("DECAY_ENABLED") == 'True'
        decay_amount = args.decay_amount or float(os.getenv("DECAY_AMOUNT"))
        grace_days = args.grace_days or int(os.getenv("DECAY_GRACE_DAYS"))
        max_decay_proportion = args.max_decay_proportion or float(os.getenv("MAX_DECAY_PROPORTION"))

        default_sigma = args.ts_default_sigma or float(os.getenv("TS_DEFAULT_SIGMA"))
        default_mu = args.ts_default_mu or float(os.getenv("TS_DEFAULT_MU"))

        verbose_output = args.verbose_output or os.getenv("VERBOSE_OUTPUT") == 'True'
        write_txt = args.write_txt or os.getenv("WRITE_TXT") == 'True'
        write_csv = args.write_csv or os.getenv("WRITE_CSV") == 'True'
        json_file = args.json_file or os.getenv("JSON_FILENAME")

        processor = GameProcessor(domain, server_id, start_date, timezone, min_games_required, last_days_threshold,
                                  min_games_last_days, discard_ties, decay_enabled, decay_amount, grace_days,
                                  max_decay_proportion, default_sigma, default_mu, verbose_output, top_x, write_txt,
                                  write_csv, json_file)
        processor.user_aliases = user_aliases
        processor.run()
    except Exception as init_variables_exception:
        handle_error(init_variables_exception, "Failed to initialize input variables")


if __name__ == "__main__":
    main()
