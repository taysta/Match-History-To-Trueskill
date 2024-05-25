import unittest
from unittest.mock import patch, mock_open, MagicMock
from datetime import datetime, timedelta
import pytz
from main import Player, GameProcessor


class TestPlayer(unittest.TestCase):
    def setUp(self):
        self.player = Player('1', 'Player1', 25.0, 8.333)

    def test_update_pick_order(self):
        self.player.update_pick_order(3)
        self.assertEqual(self.player.total_pick_order, 3)
        self.assertEqual(self.player.pick_order_count, 1)
        self.assertEqual(self.player.avg_pick_order, 3.0)

    def test_add_game(self):
        today = datetime.now().date()
        self.player.add_game(True, today, True)
        self.assertEqual(self.player.games_played, 1)
        self.assertEqual(self.player.wins, 1)
        self.assertEqual(self.player.recent_games, 1)
        self.assertEqual(self.player.last_played, today)

    def test_apply_sigma_decay(self):
        self.player.apply_sigma_decay(0.1, 0.5, 30, 8.333)
        self.assertGreaterEqual(self.player.rating.sigma, 8.333)


class TestGameProcessor(unittest.TestCase):
    def setUp(self):
        self.domain = "https://example.com"
        self.server_id = "server123"
        self.start_date = "1706338920000"  # 2024-01-27
        self.timezone = pytz.timezone("Australia/Sydney")
        self.min_games_required = 10
        self.last_days_threshold = 30
        self.min_games_last_days = 5
        self.discard_ties = False
        self.decay_enabled = True
        self.decay_amount = 0.1
        self.grace_days = 7
        self.max_decay_proportion = 0.5
        self.default_sigma = 8.333
        self.default_mu = 25.0
        self.verbose_output = False
        self.top_x = 20
        self.write_txt = False
        self.write_csv = False
        self.json_file = None

        self.processor = GameProcessor(
            self.domain, self.server_id, self.start_date, self.timezone, self.min_games_required,
            self.last_days_threshold, self.min_games_last_days, self.discard_ties, self.decay_enabled,
            self.decay_amount, self.grace_days, self.max_decay_proportion, self.default_sigma, self.default_mu,
            self.verbose_output, self.top_x, self.write_txt, self.write_csv, self.json_file
        )

    @patch('requests.get')
    def test_fetch_game_data(self, mock_get):
        mock_response = MagicMock()
        mock_response.json.return_value = {"key": "value"}
        mock_response.status_code = 200
        mock_get.return_value = mock_response

        data = self.processor.fetch_game_data()
        self.assertEqual(data, {"key": "value"})

    @patch('builtins.open', new_callable=mock_open, read_data='{"key": "value"}')
    def test_read_game_data_from_file(self, mock_file):
        self.processor.json_file = "dummy_path"
        data = self.processor.read_game_data_from_file()
        self.assertEqual(data, {"key": "value"})

    def test_get_primary_id(self):
        self.processor.user_aliases = {"main": ["alias1", "alias2"]}
        self.assertEqual(self.processor.get_primary_id("alias1"), "main")
        self.assertEqual(self.processor.get_primary_id("unknown"), "unknown")

    def test_get_player(self):
        player = self.processor.get_player("1", "Player1")
        self.assertEqual(player.user_id, "1")
        self.assertEqual(player.name, "Player1")

    def test_process_game(self):
        player1 = Player('1', 'Player1', 25.0, 8.333)
        player2 = Player('2', 'Player2', 25.0, 8.333)
        self.processor.player_ratings = {'1': player1, '2': player2}
        game_data = {
            "completionTimestamp": 1609459200000,
            "players": [
                {"user": {"id": "1", "name": "Player1"}, "team": 1, "captain": 0, "pickOrder": 3},
                {"user": {"id": "2", "name": "Player2"}, "team": 2, "captain": 0, "pickOrder": 2}
            ],
            "winningTeam": 1
        }
        played_dates = {}
        self.processor.process_game(game_data, played_dates)
        self.assertEqual(self.processor.games_used_count, 1)
        self.assertIn(datetime(2021, 1, 1, tzinfo=self.timezone).date(), played_dates)
        self.assertIn("1", played_dates[datetime(2021, 1, 1, tzinfo=self.timezone).date()])

    def test_update_ratings(self):
        player1 = Player('1', 'Player1', 25.0, 8.333)
        player2 = Player('2', 'Player2', 25.0, 8.333)
        self.processor.player_ratings = {'1': player1, '2': player2}
        team1 = [player1.rating]
        team2 = [player2.rating]
        self.processor.update_ratings(team1, ['1'], team2, ['2'], 1)
        self.assertGreater(self.processor.player_ratings['1'].rating.mu, 25.0)
        self.assertLess(self.processor.player_ratings['2'].rating.mu, 25.0)

    def test_apply_decay(self):
        player = Player('1', 'Player1', 25.0, 8.333)
        player.last_played = datetime.now(self.timezone).date() - timedelta(days=10)
        self.processor.player_ratings = {'1': player}
        played_dates = {datetime.now(self.timezone).date() - timedelta(days=i): set() for i in range(10)}
        self.processor.apply_decay(played_dates)
        self.assertGreaterEqual(self.processor.player_ratings['1'].rating.sigma, 8.333)

    @patch('sys.stdout', new_callable=unittest.mock.MagicMock)
    def test_display_ratings(self, mock_stdout):
        player = Player('1', 'Player1', 25.0, 8.333)
        player.games_played = 20
        player.last_played = datetime.now(self.timezone).date()
        self.processor.player_ratings = {'1': player}

        # Generate the end_date_str in the same way it's generated in the run method
        end_date_str = datetime.now(self.timezone).strftime('%Y-%m-%d %I:%M %p %Z')

        # Call the actual display_ratings method
        self.processor.display_ratings("2021-01-01", end_date_str, mock_stdout)

        # Check the calls to the write method
        output = mock_stdout.write.call_args_list

        self.assertTrue(any(f"Games period: From 2021-01-01 to {end_date_str}" in str(call) for call in output))
        self.assertTrue(any("Games used: 0" in str(call) for call in output))
        self.assertTrue(any("Sigma decay: decay_amount=0.1, grace_days=7, max_decay_proportion=0.5" in str(call) for call in output))
        self.assertTrue(any("Minimum games required: 10 (0 players filtered)" in str(call) for call in output))
        self.assertTrue(any("Ties discarded: False" in str(call) for call in output))
        self.assertTrue(any("Aliased player/s: " in str(call) for call in output))


if __name__ == '__main__':
    unittest.main()
