# Standard
import os
import sys
from datetime import datetime, timedelta
# External
from prettytable import PrettyTable


def ensure_directory_exists(file_path):
    directory = os.path.dirname(file_path)
    if not os.path.exists(directory):
        os.makedirs(directory)


def display_ratings(processor, start_date_str, end_date_str, stream=sys.stdout):
    current_date = datetime.now(processor.timezone).date()
    start_date_threshold = current_date - timedelta(days=processor.last_days_threshold)

    # Filter out players with less than the minimum required games played
    initial_player_count = len(processor.player_ratings)
    filtered_players = {user_id: data for user_id, data in processor.player_ratings.items() if
                        data.games_played >= processor.min_games_required}
    processor.filtered_by_min_games = initial_player_count - len(filtered_players)

    # Filter based on last_days_threshold
    if processor.last_days_threshold > 0:
        initial_filtered_count = len(filtered_players)
        filtered_players = {user_id: data for user_id, data in filtered_players.items()
                            if data.last_played >= start_date_threshold}
        processor.filtered_by_last_days = initial_filtered_count - len(filtered_players)

        # Filter based on min_games_last_days
        if processor.min_games_last_days > 0:
            initial_filtered_count = len(filtered_players)
            filtered_players = {user_id: data for user_id, data in filtered_players.items()
                                if data.recent_games >= processor.min_games_last_days}
            processor.filtered_by_min_games_last_days = initial_filtered_count - len(filtered_players)

    # Sort players by their conservative TrueSkill rating (mu - 3 * sigma)
    sorted_players = sorted(filtered_players.items(), key=lambda x: x[1].rating.mu - 3 * x[1].rating.sigma,
                            reverse=True)

    # Calculate the number of players below the cutoff
    cutoff_count = max(0, len(sorted_players) - processor.top_x) if processor.top_x > 0 else 0

    # Limit the number of players to display if processor.top_x is greater than 0
    if processor.top_x > 0:
        sorted_players = sorted_players[:processor.top_x]

    table = PrettyTable()

    if processor.verbose_output:
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

        if processor.verbose_output:
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
    if processor.decay_enabled:
        decay_settings = (f"decay_amount={processor.decay_amount}, "
                          f"grace_days={processor.grace_days}, "
                          f"max_decay_proportion={processor.max_decay_proportion}")

    # Print the output to console
    if processor.verbose_output:
        print(f"Input URL: {processor.url}", file=stream)
        print(f"Server ID: {processor.server_id}", file=stream)

    print(f"Games period: From {start_date_str} to {end_date_str}", file=stream)
    print(f"Games used: {processor.games_used_count}", file=stream)
    print(table, file=stream)
    print(f"Sigma decay: {decay_settings if processor.decay_enabled else 'Disabled'}", file=stream)
    print(f"Minimum games required: {processor.min_games_required} "
          f"({processor.filtered_by_min_games} players filtered)", file=stream)
    if processor.last_days_threshold > 0:
        print(f"Last days threshold: {processor.last_days_threshold} "
              f"({processor.filtered_by_last_days} players filtered)",
              file=stream)
        if processor.min_games_last_days > 0:
            print(f"Min games in last days threshold: {processor.min_games_last_days} "
                  f"({processor.filtered_by_min_games_last_days} players filtered)", file=stream)
    if processor.top_x > 0:
        print(f"Showing top {processor.top_x} players ({cutoff_count} cutoff)", file=stream)

    print(f"Ties discarded: {processor.discard_ties}", file=stream)
    print(f"Aliased player/s: {', '.join(processor.user_aliases.keys())}", file=stream)

    # Get current timestamp for unique filenames
    timestamp = datetime.now(processor.timezone).strftime('%Y%m%d_%H%M%S')

    # Save the text output to a text file if enabled
    if processor.write_txt:
        txt_filename = f"out/player_ratings_{timestamp}.txt"
        ensure_directory_exists(txt_filename)
        with open(txt_filename, "w", encoding="utf-8") as text_file:
            if processor.verbose_output:
                text_file.write(f"Input URL: {processor.url}\n")
                text_file.write(f"Server ID: {processor.server_id}\n")
            text_file.write(f"Games period: From {start_date_str} to {end_date_str}\n")
            text_file.write(f"Games used: {processor.games_used_count}\n")
            text_file.write(str(table))
            text_file.write(f"\nRating decay: {decay_settings if processor.decay_enabled else 'Disabled'}\n")
            text_file.write(f"Minimum games required: {processor.min_games_required} "
                            f"({processor.filtered_by_min_games} players filtered)\n")
            if processor.last_days_threshold > 0:
                text_file.write(f"Last days threshold: {processor.last_days_threshold} "
                                f"({processor.filtered_by_last_days} players filtered)\n")
                if processor.min_games_last_days > 0:
                    text_file.write(f"Min games in last days threshold: {processor.min_games_last_days} "
                                    f"({processor.filtered_by_min_games_last_days} players filtered)\n")
            if processor.top_x > 0:
                text_file.write(f"Showing top {processor.top_x} players ({cutoff_count} cutoff)\n")
            text_file.write(f"Ties discarded: {processor.discard_ties}\n")
            text_file.write(f"Aliased player/s: {', '.join(processor.user_aliases.keys())}\n")

    # Save the table to a CSV file if enabled
    if processor.write_csv:
        csv_filename = f"out/player_ratings_{timestamp}.csv"
        ensure_directory_exists(csv_filename)
        with open(csv_filename, "w", encoding="utf-8") as csv_file:
            if processor.verbose_output:
                csv_file.write("Rank,Name,Trueskill Rating (μ - 3*σ),μ (mu),σ (sigma),Games Played,"
                               "Win/Loss,Last Played,Avg Pick Order,Discord ID/s\n")
            else:
                csv_file.write("Rank,Name,Trueskill Rating (μ - 3*σ),μ (mu),σ (sigma),Games Played,"
                               "Win/Loss,Last Played,Avg Pick Order\n")
            for row in rows:
                csv_file.write(",".join(map(str, row)) + "\n")
