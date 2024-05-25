# Standard
import argparse
# Internal
from input import InputHandler
from process import GameProcessor
from shared import handle_error


# Main execution
def main():
    parser = argparse.ArgumentParser(description='Process team game match history into TrueSkill data.')
    parser.add_argument('--settings', type=str, default='settings.json', help='Path to settings JSON file')
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
        input_handler = InputHandler(args)
        input_handler.set_handler()
        settings = input_handler.get_settings()

        processor = GameProcessor(**settings)
        processor.user_aliases = settings['user_aliases']
        processor.run()
    except Exception as init_variables_exception:
        handle_error(init_variables_exception, "Failed to initialize input variables")


if __name__ == "__main__":
    main()
