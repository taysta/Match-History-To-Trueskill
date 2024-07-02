# Standard
import requests
import json
from datetime import datetime, timedelta
# External
from trueskill import Rating, rate
# Internal
from output import display_ratings
from shared import handle_error


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
                 json_file, user_aliases):
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
        self.user_aliases = user_aliases
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
            self.update_team_stats(team1_ids, new_team1_ratings)
            self.update_team_stats(team2_ids, new_team2_ratings)
        else:
            new_team2_ratings, new_team1_ratings = rate([team2, team1])
            self.update_team_stats(team2_ids, new_team2_ratings)
            self.update_team_stats(team1_ids, new_team1_ratings)

    def update_team_stats(self, team_ids, new_ratings):
        for i, user_id in enumerate(team_ids):
            player = self.player_ratings[user_id]
            player.rating = new_ratings[i]

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

        if self.decay_enabled:
            self.apply_decay(played_dates)

        display_ratings(self, start_date_str, end_date_str)
