from __future__ import annotations

import argparse
import csv
import math
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path


RANKS = '6789TJQKA'
SUITS = 'cdhs'


CORE_COLUMNS = [
    'chal_forced_takes',
    'chal_forced_takes_deck_ge5',
    'chal_forced_takes_deck_1_4',
    'chal_forced_takes_deck_0',
    'chal_first_deck0_forced_take',
    'chal_first_deck0_forced_take_battle',
    'chal_first_deck0_forced_take_table_cards',
    'chal_first_deck0_forced_take_uncovered',
    'chal_first_deck0_forced_take_attack_cards',
    'chal_first_deck0_forced_take_trump_attacks',
    'chal_first_deck0_forced_take_defender_trumps',
    'chal_first_deck0_forced_take_attacker_trumps',
    'chal_first_deck0_forced_take_attacker_nontrump_throwins',
    'chal_first_deck0_forced_take_attacker_trump_throwins',
    'chal_first_deck0_forced_take_legal_defense_cards',
    'chal_first_deck0_forced_take_legal_trump_defenses',
    'chal_first_deck0_forced_take_legal_nontrump_defenses',
    'chal_first_deck0_forced_take_coverable_uncovered',
    'chal_first_deck0_forced_take_uncoverable_uncovered',
    'chal_first_deck0_forced_take_cheapest_cover_rank',
    'chal_first_deck0_forced_take_cheapest_cover_is_trump',
    'chal_first_deck0_forced_take_opp_later_trump_attack',
    'chal_first_deck0_forced_take_prior_attack_seen',
    'chal_first_deck0_forced_take_prior_attack_chosen_is_trump',
    'chal_first_deck0_forced_take_prior_attack_cover_is_trump',
    'chal_first_deck0_forced_take_prior_attack_cover_same_rank',
    'chal_first_deck0_forced_take_prior_attack_legal_nontrumps',
    'chal_first_deck0_forced_take_prior_attack_legal_trumps',
    'chal_first_deck0_forced_take_prior_attack_chosen_forces_take',
    'chal_first_deck0_forced_take_prior_attack_chosen_forces_high_trump_cover',
    'chal_first_deck0_forced_take_prior_attack_attacker_trumps',
    'chal_first_deck0_forced_take_prior_attack_defender_trumps',
    'chal_first_deck0_forced_take_prior_attack_defender_high_trumps',
    'chal_first_deck0_forced_take_prior_attack_defender_trumps_after_cover',
    'chal_first_deck0_forced_take_prior_attack_defender_high_trumps_after_cover',
    'chal_first_deck0_forced_take_prior_attack_battles_until_forced_take',
    'chal_first_deck0_forced_take_prior_attack_self_attack_cards_after_cover',
    'chal_first_deck0_forced_take_prior_attack_self_legal_trump_options_after_cover',
    'chal_first_deck0_forced_take_prior_attack_self_trump_attacks_after_cover',
    'chal_first_deck0_forced_take_prior_attack_opp_attack_cards_after_cover',
    'chal_first_deck0_forced_take_prior_attack_opp_trump_attacks_after_cover',
    'chal_first_deck0_forced_take_prior_attack_opp_high_trump_attacks_after_cover',
    'chal_deck0_attack_decisions',
    'chal_deck0_attack_passes_with_trump',
    'chal_deck0_attack_nontrump_with_trump',
    'chal_deck0_attack_trump_with_trump',
    'chal_deck0_legal_trump_attack_options',
    'chal_deck0_legal_high_trump_attack_options',
    'chal_deck0_high_trump_attacks',
    'chal_deck0_last_two_passes_with_trump',
    'chal_deck0_last_two_nontrump_with_trump',
    'chal_deck0_last_two_trump_with_trump',
    'chal_voluntary_takes',
    'chal_vol_take_high_trump_deck_ge5',
    'chal_cards_taken',
    'chal_cards_taken_deck_ge5',
    'chal_cards_taken_deck_1_4',
    'chal_cards_taken_deck_0',
    'opp_cards_taken',
    'opp_cards_taken_deck_ge5',
    'opp_cards_taken_deck_1_4',
    'opp_cards_taken_deck_0',
    'deck_empty_after_battle',
    'max_cards_taken',
    'chal_initial_trumps',
    'opp_initial_trumps',
    'chal_initial_high_trumps',
    'opp_initial_high_trumps',
    'chal_attack_cards',
    'opp_attack_cards',
    'chal_trump_attack_cards',
    'chal_trump_attack_cards_deck_ge5',
    'chal_trump_attack_cards_deck_1_4',
    'chal_trump_attack_cards_deck_0',
    'opp_trump_attack_cards',
    'opp_trump_attack_cards_deck_ge5',
    'opp_trump_attack_cards_deck_1_4',
    'opp_trump_attack_cards_deck_0',
    'chal_trump_defense_cards',
    'opp_trump_defense_cards',
    'chal_draws',
    'opp_draws',
    'chal_final_hand_count',
    'opp_final_hand_count',
    'chal_final_trumps',
    'opp_final_trumps',
    'chal_final_high_trumps',
    'opp_final_high_trumps',
    'chal_final_non_trumps',
    'opp_final_non_trumps',
    'battles',
    'table_cards_total',
]

PREDICATES = [
    ('chal_forced_takes>=1', lambda row: value(row, 'chal_forced_takes') >= 1),
    ('chal_forced_takes>=2', lambda row: value(row, 'chal_forced_takes') >= 2),
    ('chal_forced_takes_deck_ge5>=1', lambda row: value(row, 'chal_forced_takes_deck_ge5') >= 1),
    ('chal_forced_takes_deck_1_4>=1', lambda row: value(row, 'chal_forced_takes_deck_1_4') >= 1),
    ('chal_forced_takes_deck_0>=1', lambda row: value(row, 'chal_forced_takes_deck_0') >= 1),
    ('chal_first_deck0_forced_take', lambda row: value(row, 'chal_first_deck0_forced_take') == 1),
    (
        'chal_first_deck0_forced_take_table<=3',
        lambda row: value(row, 'chal_first_deck0_forced_take') == 1
        and value(row, 'chal_first_deck0_forced_take_table_cards') <= 3,
    ),
    (
        'chal_first_deck0_forced_take_defender_trumps==0',
        lambda row: value(row, 'chal_first_deck0_forced_take') == 1
        and value(row, 'chal_first_deck0_forced_take_defender_trumps') == 0,
    ),
    (
        'chal_first_deck0_forced_take_attacker_trumps>=1',
        lambda row: value(row, 'chal_first_deck0_forced_take') == 1
        and value(row, 'chal_first_deck0_forced_take_attacker_trumps') >= 1,
    ),
    (
        'chal_first_deck0_forced_take_no_nt_throwins',
        lambda row: value(row, 'chal_first_deck0_forced_take') == 1
        and value(row, 'chal_first_deck0_forced_take_attacker_nontrump_throwins') == 0,
    ),
    (
        'chal_first_deck0_forced_take_trump_throwin_available',
        lambda row: value(row, 'chal_first_deck0_forced_take') == 1
        and value(row, 'chal_first_deck0_forced_take_attacker_trump_throwins') >= 1,
    ),
    (
        'chal_first_deck0_forced_take_any_legal_defense',
        lambda row: value(row, 'chal_first_deck0_forced_take') == 1
        and value(row, 'chal_first_deck0_forced_take_legal_defense_cards') >= 1,
    ),
    (
        'chal_first_deck0_forced_take_legal_trump_defense',
        lambda row: value(row, 'chal_first_deck0_forced_take') == 1
        and value(row, 'chal_first_deck0_forced_take_legal_trump_defenses') >= 1,
    ),
    (
        'chal_first_deck0_forced_take_no_legal_defense',
        lambda row: value(row, 'chal_first_deck0_forced_take') == 1
        and value(row, 'chal_first_deck0_forced_take_legal_defense_cards') == 0,
    ),
    (
        'chal_first_deck0_forced_take_opp_later_trump_attack',
        lambda row: value(row, 'chal_first_deck0_forced_take_opp_later_trump_attack') == 1,
    ),
    (
        'chal_prior_deck0_attack_seen_before_forced_take',
        lambda row: value(row, 'chal_first_deck0_forced_take_prior_attack_seen') == 1,
    ),
    (
        'chal_prior_attack_had_trump_option',
        lambda row: value(row, 'chal_first_deck0_forced_take') == 1
        and value(row, 'chal_first_deck0_forced_take_prior_attack_legal_trumps') >= 1,
    ),
    (
        'chal_prior_attack_chose_nontrump_with_trump_option',
        lambda row: value(row, 'chal_first_deck0_forced_take') == 1
        and value(row, 'chal_first_deck0_forced_take_prior_attack_legal_trumps') >= 1
        and value(row, 'chal_first_deck0_forced_take_prior_attack_chosen_is_trump') == 0,
    ),
    (
        'chal_prior_attack_had_force_take_option',
        lambda row: value(row, 'chal_first_deck0_forced_take') == 1
        and value(row, 'chal_first_deck0_forced_take_prior_attack_legal_force_take_attack_mask') > 0,
    ),
    (
        'chal_prior_attack_had_force_high_trump_cover_option',
        lambda row: value(row, 'chal_first_deck0_forced_take') == 1
        and value(row, 'chal_first_deck0_forced_take_prior_attack_legal_force_high_trump_cover_attack_mask') > 0,
    ),
    (
        'chal_prior_attack_chosen_forces_take',
        lambda row: value(row, 'chal_first_deck0_forced_take_prior_attack_chosen_forces_take') == 1,
    ),
    (
        'chal_prior_attack_chosen_forces_high_trump_cover',
        lambda row: value(
            row, 'chal_first_deck0_forced_take_prior_attack_chosen_forces_high_trump_cover'
        )
        == 1,
    ),
    (
        'chal_prior_attack_defender_kept_trump',
        lambda row: value(row, 'chal_first_deck0_forced_take') == 1
        and value(row, 'chal_first_deck0_forced_take_prior_attack_defender_trumps') >= 1,
    ),
    (
        'chal_prior_attack_defender_kept_high_trump',
        lambda row: value(row, 'chal_first_deck0_forced_take') == 1
        and value(row, 'chal_first_deck0_forced_take_prior_attack_defender_high_trumps') >= 1,
    ),
    (
        'chal_prior_attack_covered_by_trump',
        lambda row: value(row, 'chal_first_deck0_forced_take') == 1
        and value(row, 'chal_first_deck0_forced_take_prior_attack_cover_is_trump') == 1,
    ),
    (
        'chal_prior_attack_same_rank_cover',
        lambda row: value(row, 'chal_first_deck0_forced_take') == 1
        and value(row, 'chal_first_deck0_forced_take_prior_attack_cover_same_rank') == 1,
    ),
    (
        'chal_prior_attack_high_trump_after_cover',
        lambda row: value(row, 'chal_first_deck0_forced_take') == 1
        and value(row, 'chal_first_deck0_forced_take_prior_attack_defender_high_trumps_after_cover') >= 1,
    ),
    (
        'chal_prior_cover_then_opp_trump_attack',
        lambda row: value(row, 'chal_first_deck0_forced_take') == 1
        and value(row, 'chal_first_deck0_forced_take_prior_attack_opp_trump_attacks_after_cover') >= 1,
    ),
    (
        'chal_prior_cover_then_opp_high_trump_attack',
        lambda row: value(row, 'chal_first_deck0_forced_take') == 1
        and value(row, 'chal_first_deck0_forced_take_prior_attack_opp_high_trump_attacks_after_cover') >= 1,
    ),
    (
        'chal_prior_cover_then_self_trump_option',
        lambda row: value(row, 'chal_first_deck0_forced_take') == 1
        and value(row, 'chal_first_deck0_forced_take_prior_attack_self_legal_trump_options_after_cover') >= 1,
    ),
    ('chal_voluntary_takes>=2', lambda row: value(row, 'chal_voluntary_takes') >= 2),
    ('chal_cards_taken>=6', lambda row: value(row, 'chal_cards_taken') >= 6),
    ('chal_cards_taken>=8', lambda row: value(row, 'chal_cards_taken') >= 8),
    ('chal_cards_taken_deck_0>=4', lambda row: value(row, 'chal_cards_taken_deck_0') >= 4),
    ('opp_cards_taken<=2', lambda row: value(row, 'opp_cards_taken') <= 2),
    ('opp_cards_taken==0', lambda row: value(row, 'opp_cards_taken') == 0),
    ('chal_trump_attack_cards==0', lambda row: value(row, 'chal_trump_attack_cards') == 0),
    ('chal_trump_attack_cards>=2', lambda row: value(row, 'chal_trump_attack_cards') >= 2),
    ('chal_trump_attack_cards_deck_0>=1', lambda row: value(row, 'chal_trump_attack_cards_deck_0') >= 1),
    ('opp_trump_attack_cards>=1', lambda row: value(row, 'opp_trump_attack_cards') >= 1),
    ('opp_trump_attack_cards_deck_0>=1', lambda row: value(row, 'opp_trump_attack_cards_deck_0') >= 1),
    ('opp_forced_takes==0', lambda row: value(row, 'opp_forced_takes') == 0),
    ('max_cards_taken<=3', lambda row: value(row, 'max_cards_taken') <= 3),
    ('chal_initial_trumps==0', lambda row: value(row, 'chal_initial_trumps') == 0),
    ('chal_initial_high_trumps==0', lambda row: value(row, 'chal_initial_high_trumps') == 0),
    (
        'chal_lost_with_lone_nontrump',
        lambda row: value(row, 'challenger_points') == 0
        and value(row, 'chal_final_hand_count') == 1
        and value(row, 'chal_final_non_trumps') == 1,
    ),
    (
        'chal_lost_with_trump_left',
        lambda row: value(row, 'challenger_points') == 0
        and value(row, 'chal_final_trumps') >= 1,
    ),
    ('chal_deck0_passed_with_trump', lambda row: value(row, 'chal_deck0_attack_passes_with_trump') >= 1),
    (
        'chal_deck0_nontrump_with_trump',
        lambda row: value(row, 'chal_deck0_attack_nontrump_with_trump') >= 1,
    ),
    (
        'chal_deck0_last_two_nontrump_or_pass_with_trump',
        lambda row: value(row, 'chal_deck0_last_two_passes_with_trump')
        + value(row, 'chal_deck0_last_two_nontrump_with_trump') >= 1,
    ),
]

SKIP_GAP_COLUMNS = {
    'seed',
    'game_in_pair',
    'deck_seed',
    'rng_seed',
    'challenger_seat',
    'pair_score',
    'challenger_points',
    'initial_attacker',
    'challenger_attacked_first',
    'trump_rank',
    'trump_suit',
    'final_attacker',
}


def value(row: dict[str, str], column: str) -> float:
    return float(row[column])


def card_name(card: int) -> str:
    if card < 0:
        return '--'
    return f'{RANKS[card // 4]}{SUITS[card % 4]}'


def rank_suit_name(rank: int, suit: int) -> str:
    if rank < 0 or suit < 0:
        return '--'
    return f'{RANKS[rank]}{SUITS[suit]}'


def mask_cards(mask_value: float) -> str:
    mask = int(mask_value)
    cards = [card_name(card) for card in range(36) if mask & (1 << card)]
    return ','.join(cards) if cards else '-'


def mask_popcount(mask_value: float) -> int:
    return int(mask_value).bit_count()


def mask_has_trump(mask_value: float, trump_suit: int) -> bool:
    mask = int(mask_value)
    for card in range(36):
        if mask & (1 << card) and card % 4 == trump_suit:
            return True
    return False


def mask_has_high_trump(mask_value: float, trump_suit: int) -> bool:
    mask = int(mask_value)
    for card in range(36):
        if mask & (1 << card) and card % 4 == trump_suit and card // 4 >= 2:
            return True
    return False


def mask_has_rank(mask_value: float, rank: int) -> bool:
    if rank < 0:
        return False
    mask = int(mask_value)
    for suit in range(4):
        if mask & (1 << (rank * 4 + suit)):
            return True
    return False


def mask_intersects(left: float, right: float) -> bool:
    return (int(left) & int(right)) != 0


def high_trump_mask(mask_value: float, trump_suit: int) -> int:
    mask = int(mask_value)
    return sum(
        1 << card
        for card in range(36)
        if mask & (1 << card) and card % 4 == trump_suit and card // 4 >= 2
    )


def rank_mask_from_cards(mask_value: int | float) -> int:
    mask = int(mask_value)
    rank_mask = 0
    for card in range(36):
        if mask & (1 << card):
            rank_mask |= 1 << (card // 4)
    return rank_mask


def rank_mask_names(mask_value: int | float) -> str:
    mask = int(mask_value)
    ranks = [RANKS[rank] for rank in range(9) if mask & (1 << rank)]
    return ','.join(ranks) if ranks else '-'


def hand_bucket(count: float) -> str:
    n = int(count)
    if n <= 1:
        return str(n)
    if n == 2:
        return '2'
    return '3+'


def trump_bucket(count: float) -> str:
    n = int(count)
    if n == 0:
        return '0'
    if n == 1:
        return '1'
    return '2+'


def challenger_is_final_attacker(row: dict[str, str]) -> bool:
    return int(value(row, 'final_attacker')) == int(value(row, 'challenger_seat'))


@dataclass
class Stats:
    count: int = 0
    sums: dict[str, float] = field(default_factory=lambda: defaultdict(float))
    sums_sq: dict[str, float] = field(default_factory=lambda: defaultdict(float))

    def add(self, row: dict[str, str], columns: list[str]) -> None:
        self.count += 1
        for column in columns:
            value = float(row[column])
            self.sums[column] += value
            self.sums_sq[column] += value * value

    def mean(self, column: str) -> float:
        return self.sums[column] / self.count if self.count else 0.0

    def std(self, column: str) -> float:
        if self.count <= 1:
            return 0.0
        mean = self.mean(column)
        var = self.sums_sq[column] / self.count - mean * mean
        return math.sqrt(max(0.0, var))


@dataclass
class EventStats:
    count: int = 0
    sums: dict[str, float] = field(default_factory=lambda: defaultdict(float))

    def add(self, row: dict[str, str], columns: list[str]) -> None:
        if value(row, 'chal_first_deck0_forced_take') != 1:
            return
        self.count += 1
        for column in columns:
            self.sums[column] += value(row, column)

    def mean(self, column: str) -> float:
        return self.sums[column] / self.count if self.count else 0.0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Summarize B2-vs-B4 per-game feature TSVs by macro outcome buckets.'
    )
    parser.add_argument('features_tsv', type=Path)
    parser.add_argument('--top', type=int, default=12)
    return parser.parse_args()


def numeric_columns(fieldnames: list[str]) -> list[str]:
    text_columns = {'challenger', 'opponent', 'result', 'pair_bucket'}
    return [name for name in fieldnames if name not in text_columns]


def print_bucket_summary(groups: dict[str, Stats], total_rows: int) -> None:
    print('bucket summary')
    print('bucket\trows\tshare\tmean_points\tmean_pair_score')
    for bucket in ['win', 'split', 'loss']:
        stats = groups[bucket]
        share = stats.count / total_rows if total_rows else 0.0
        print(
            f'{bucket}\t{stats.count}\t{share:.4f}\t'
            f'{stats.mean("challenger_points"):.4f}\t{stats.mean("pair_score"):.4f}'
        )


def print_core_means(groups: dict[str, Stats]) -> None:
    print()
    print('core feature means by pair bucket')
    print('feature\twin\tsplit\tloss\tloss-win\tsplit-win')
    for column in CORE_COLUMNS:
        win = groups['win'].mean(column)
        split = groups['split'].mean(column)
        loss = groups['loss'].mean(column)
        print(f'{column}\t{win:.4f}\t{split:.4f}\t{loss:.4f}\t{loss - win:+.4f}\t{split - win:+.4f}')


def print_predicate_rates(predicate_counts: dict[str, dict[str, int]], groups: dict[str, Stats]) -> None:
    print()
    print('threshold rates by pair bucket')
    print('predicate\twin\tsplit\tloss\tloss-win\tsplit-win')
    for label, _ in PREDICATES:
        win = predicate_counts['win'][label] / groups['win'].count
        split = predicate_counts['split'][label] / groups['split'].count
        loss = predicate_counts['loss'][label] / groups['loss'].count
        print(f'{label}\t{win:.4f}\t{split:.4f}\t{loss:.4f}\t{loss - win:+.4f}\t{split - win:+.4f}')


def pooled_std(left: Stats, right: Stats, column: str) -> float:
    left_var = left.std(column) ** 2
    right_var = right.std(column) ** 2
    return math.sqrt((left_var + right_var) / 2.0)


def print_top_gaps(groups: dict[str, Stats], columns: list[str], top: int, compare: str) -> None:
    rows = []
    win = groups['win']
    other = groups[compare]
    for column in columns:
        if column in SKIP_GAP_COLUMNS:
            continue
        std = pooled_std(win, other, column)
        if std == 0.0:
            continue
        gap = other.mean(column) - win.mean(column)
        signed_std_gap = gap / std
        rows.append((abs(signed_std_gap), signed_std_gap, gap, column, win.mean(column), other.mean(column)))

    print()
    print(f'top standardized {compare}-minus-win gaps')
    print('feature\twin\t' + compare + '\tdelta\tstd_delta')
    for _, signed_std_gap, gap, column, win_mean, other_mean in sorted(rows, reverse=True)[:top]:
        print(f'{column}\t{win_mean:.4f}\t{other_mean:.4f}\t{gap:+.4f}\t{signed_std_gap:+.3f}')


def print_point_summary(groups: dict[str, Stats], total_rows: int) -> None:
    print()
    print('individual game points summary')
    print('points\trows\tshare\tforced_takes\tvol_takes\tcards_taken\topp_cards_taken')
    for points in ['1.0', '0.5', '0.0']:
        stats = groups[points]
        share = stats.count / total_rows if total_rows else 0.0
        print(
            f'{points}\t{stats.count}\t{share:.4f}\t'
            f'{stats.mean("chal_forced_takes"):.4f}\t{stats.mean("chal_voluntary_takes"):.4f}\t'
            f'{stats.mean("chal_cards_taken"):.4f}\t{stats.mean("opp_cards_taken"):.4f}'
        )


def print_first_event_summary(groups: dict[str, EventStats], bucket_groups: dict[str, Stats]) -> None:
    event_columns = [
        'chal_first_deck0_forced_take_table_cards',
        'chal_first_deck0_forced_take_attack_cards',
        'chal_first_deck0_forced_take_trump_attacks',
        'chal_first_deck0_forced_take_defender_hand_count',
        'chal_first_deck0_forced_take_defender_trumps',
        'chal_first_deck0_forced_take_attacker_hand_count',
        'chal_first_deck0_forced_take_attacker_trumps',
        'chal_first_deck0_forced_take_attacker_nontrump_throwins',
        'chal_first_deck0_forced_take_attacker_trump_throwins',
        'chal_first_deck0_forced_take_legal_defense_cards',
        'chal_first_deck0_forced_take_legal_trump_defenses',
        'chal_first_deck0_forced_take_legal_nontrump_defenses',
        'chal_first_deck0_forced_take_coverable_uncovered',
        'chal_first_deck0_forced_take_uncoverable_uncovered',
        'chal_first_deck0_forced_take_cheapest_cover_rank',
        'chal_first_deck0_forced_take_cheapest_cover_is_trump',
        'chal_first_deck0_forced_take_opp_later_trump_attack',
        'chal_first_deck0_forced_take_prior_attack_seen',
        'chal_first_deck0_forced_take_prior_attack_chosen_is_trump',
        'chal_first_deck0_forced_take_prior_attack_chosen_rank',
        'chal_first_deck0_forced_take_prior_attack_legal_nontrumps',
        'chal_first_deck0_forced_take_prior_attack_legal_trumps',
        'chal_first_deck0_forced_take_prior_attack_chosen_forces_take',
        'chal_first_deck0_forced_take_prior_attack_chosen_forces_high_trump_cover',
        'chal_first_deck0_forced_take_prior_attack_attacker_trumps',
        'chal_first_deck0_forced_take_prior_attack_defender_trumps',
        'chal_first_deck0_forced_take_prior_attack_defender_high_trumps',
        'chal_first_deck0_forced_take_prior_attack_covered',
        'chal_first_deck0_forced_take_prior_attack_cover_is_trump',
        'chal_first_deck0_forced_take_prior_attack_cover_same_rank',
        'chal_first_deck0_forced_take_prior_attack_cover_rank',
        'chal_first_deck0_forced_take_prior_attack_defender_trumps_after_cover',
        'chal_first_deck0_forced_take_prior_attack_defender_high_trumps_after_cover',
        'chal_first_deck0_forced_take_prior_attack_battles_until_forced_take',
        'chal_first_deck0_forced_take_prior_attack_self_attack_cards_after_cover',
        'chal_first_deck0_forced_take_prior_attack_self_legal_trump_options_after_cover',
        'chal_first_deck0_forced_take_prior_attack_self_trump_attacks_after_cover',
        'chal_first_deck0_forced_take_prior_attack_opp_attack_cards_after_cover',
        'chal_first_deck0_forced_take_prior_attack_opp_trump_attacks_after_cover',
        'chal_first_deck0_forced_take_prior_attack_opp_high_trump_attacks_after_cover',
        'chal_deck0_attack_passes_with_trump',
        'chal_deck0_attack_nontrump_with_trump',
        'chal_deck0_attack_trump_with_trump',
        'chal_deck0_legal_high_trump_attack_options',
        'chal_deck0_high_trump_attacks',
        'chal_deck0_last_two_passes_with_trump',
        'chal_deck0_last_two_nontrump_with_trump',
        'chal_deck0_last_two_trump_with_trump',
    ]
    print()
    print('first chal deck-empty forced-take event means (conditional on event)')
    print('feature\twin\tsplit\tloss')
    for column in event_columns:
        values = [groups[bucket].mean(column) for bucket in ['win', 'split', 'loss']]
        print(f'{column}\t{values[0]:.4f}\t{values[1]:.4f}\t{values[2]:.4f}')

    print()
    print('first chal deck-empty forced-take event prevalence')
    print('bucket\tevent_rows\tbucket_rows\tevent_rate')
    for bucket in ['win', 'split', 'loss']:
        event_count = groups[bucket].count
        bucket_count = bucket_groups[bucket].count
        rate = event_count / bucket_count if bucket_count else 0.0
        print(f'{bucket}\t{event_count}\t{bucket_count}\t{rate:.4f}')


def print_pair_event_summary(rows_by_seed: dict[str, list[dict[str, str]]]) -> None:
    groups: dict[str, dict[int, int]] = defaultdict(lambda: defaultdict(int))
    score_groups: dict[str, dict[float, int]] = defaultdict(lambda: defaultdict(int))
    event_loss_rows: dict[str, int] = defaultdict(int)
    total_rows: dict[str, int] = defaultdict(int)

    for rows in rows_by_seed.values():
        if not rows:
            continue
        bucket = rows[0]['pair_bucket']
        pair_score = value(rows[0], 'pair_score')
        event_games = sum(int(value(row, 'chal_first_deck0_forced_take') == 1) for row in rows)
        groups[bucket][event_games] += 1
        score_groups[bucket][pair_score] += 1
        for row in rows:
            total_rows[bucket] += 1
            if value(row, 'chal_first_deck0_forced_take') == 1 and value(row, 'challenger_points') == 0:
                event_loss_rows[bucket] += 1

    print()
    print('pair-level first forced-take event counts')
    print('bucket\tevent_games_0\tevent_games_1\tevent_games_2')
    for bucket in ['win', 'split', 'loss']:
        print(
            f'{bucket}\t{groups[bucket][0]}\t{groups[bucket][1]}\t{groups[bucket][2]}'
        )

    print()
    print('pair-level score distribution')
    print('bucket\tpair_score\tseeds')
    for bucket in ['win', 'split', 'loss']:
        for score, count in sorted(score_groups[bucket].items()):
            print(f'{bucket}\t{score:.2f}\t{count}')

    print()
    print('event rows that are individual-game losses')
    print('bucket\tevent_loss_rows\tall_rows\tshare')
    for bucket in ['win', 'split', 'loss']:
        share = event_loss_rows[bucket] / total_rows[bucket] if total_rows[bucket] else 0.0
        print(f'{bucket}\t{event_loss_rows[bucket]}\t{total_rows[bucket]}\t{share:.4f}')


def print_no_event_loss_summary(rows_by_seed: dict[str, list[dict[str, str]]]) -> None:
    rows = []
    pair_scores: dict[float, int] = defaultdict(int)
    for seed_rows in rows_by_seed.values():
        if not seed_rows or seed_rows[0]['pair_bucket'] != 'loss':
            continue
        event_games = sum(int(value(row, 'chal_first_deck0_forced_take') == 1) for row in seed_rows)
        if event_games != 0:
            continue
        pair_scores[value(seed_rows[0], 'pair_score')] += 1
        rows.extend(seed_rows)

    if not rows:
        return

    columns = [
        'chal_forced_takes_deck_0',
        'chal_trump_attack_cards_deck_0',
        'opp_trump_attack_cards_deck_0',
        'chal_cards_taken',
        'opp_cards_taken',
        'chal_final_hand_count',
        'opp_final_hand_count',
        'chal_final_trumps',
        'opp_final_trumps',
        'chal_final_high_trumps',
        'opp_final_high_trumps',
        'chal_final_non_trumps',
        'opp_final_non_trumps',
        'chal_final_min_trump_rank',
        'chal_final_min_non_trump_rank',
        'chal_final_max_trump_rank',
        'chal_final_max_non_trump_rank',
        'chal_initial_trumps',
        'opp_initial_trumps',
    ]
    stats = Stats()
    for row in rows:
        stats.add(row, columns)

    print()
    print('B4 pair wins without chal first deck-empty forced-take event')
    print('pair_score\tseeds')
    for score, count in sorted(pair_scores.items()):
        print(f'{score:.2f}\t{count}')
    print('feature\tmean')
    for column in columns:
        print(f'{column}\t{stats.mean(column):.4f}')

    predicates = {
        'chal_lost_with_lone_nontrump': lambda row: value(row, 'challenger_points') == 0
        and value(row, 'chal_final_hand_count') == 1
        and value(row, 'chal_final_non_trumps') == 1,
        'chal_lost_with_trump_left': lambda row: value(row, 'challenger_points') == 0
        and value(row, 'chal_final_trumps') >= 1,
        'opp_won_with_trump_left': lambda row: value(row, 'challenger_points') == 0
        and value(row, 'opp_final_trumps') >= 1,
    }
    print('predicate\trate')
    for label, predicate in predicates.items():
        count = sum(int(predicate(row)) for row in rows)
        print(f'{label}\t{count / len(rows):.4f}')

    split_columns = [
        'chal_final_hand_count',
        'chal_final_trumps',
        'chal_final_high_trumps',
        'chal_final_non_trumps',
        'chal_final_min_trump_rank',
        'chal_final_max_trump_rank',
        'chal_cards_taken',
        'chal_trump_attack_cards_deck_0',
        'opp_trump_attack_cards_deck_0',
        'chal_deck0_attack_passes_with_trump',
        'chal_deck0_attack_nontrump_with_trump',
        'chal_deck0_legal_high_trump_attack_options',
        'chal_deck0_high_trump_attacks',
        'chal_deck0_last_two_passes_with_trump',
        'chal_deck0_last_two_nontrump_with_trump',
    ]
    split_stats: dict[str, Stats] = defaultdict(Stats)
    for row in rows:
        split_stats[row['challenger_points']].add(row, split_columns)

    print()
    print('no-event B4 pair wins by individual challenger points')
    print('points\trows\tfinal_hand\tfinal_trumps\tfinal_high_trumps\tfinal_nontrumps\tcards_taken')
    for points in ['0.0', '0.5', '1.0']:
        stats = split_stats[points]
        if stats.count == 0:
            continue
        print(
            f'{points}\t{stats.count}\t{stats.mean("chal_final_hand_count"):.4f}\t'
            f'{stats.mean("chal_final_trumps"):.4f}\t{stats.mean("chal_final_high_trumps"):.4f}\t'
            f'{stats.mean("chal_final_non_trumps"):.4f}\t{stats.mean("chal_cards_taken"):.4f}'
        )

    strata: dict[tuple[str, str], Stats] = defaultdict(Stats)
    for row in rows:
        if row['challenger_points'] != '0.0':
            continue
        key = (hand_bucket(value(row, 'chal_final_hand_count')), trump_bucket(value(row, 'chal_final_trumps')))
        strata[key].add(row, split_columns)

    print()
    print('no-event B4 individual losses by final hand/trump stratum')
    print('final_hand\tfinal_trumps\trows\tfinal_high_trumps\tfinal_nontrumps\tmin_trump\tmax_trump\tcards_taken')
    for (hand, trumps), stats in sorted(strata.items()):
        print(
            f'{hand}\t{trumps}\t{stats.count}\t{stats.mean("chal_final_high_trumps"):.4f}\t'
            f'{stats.mean("chal_final_non_trumps"):.4f}\t{stats.mean("chal_final_min_trump_rank"):.4f}\t'
            f'{stats.mean("chal_final_max_trump_rank"):.4f}\t{stats.mean("chal_cards_taken"):.4f}'
        )


def print_forced_take_representatives(rows_by_seed: dict[str, list[dict[str, str]]], limit: int = 12) -> None:
    groups: dict[str, list[dict[str, str]]] = defaultdict(list)
    group_counts: dict[str, int] = defaultdict(int)
    group_has_reply_rank: dict[str, int] = defaultdict(int)
    group_has_trump: dict[str, int] = defaultdict(int)
    group_force_take_option: dict[str, int] = defaultdict(int)
    group_force_high_option: dict[str, int] = defaultdict(int)
    group_chosen_force_take: dict[str, int] = defaultdict(int)
    group_chosen_force_high: dict[str, int] = defaultdict(int)
    group_prior_legal_trumps: dict[str, float] = defaultdict(float)
    group_prior_trumps: dict[str, float] = defaultdict(float)
    for rows in rows_by_seed.values():
        for row in rows:
            if row['pair_bucket'] != 'loss':
                continue
            if row['challenger_points'] != '0.0':
                continue
            if value(row, 'chal_first_deck0_forced_take') != 1:
                continue
            if value(row, 'chal_first_deck0_forced_take_prior_attack_seen') != 1:
                continue

            trump_suit = int(value(row, 'trump_suit'))
            attack_mask = value(row, 'chal_first_deck0_forced_take_attack_mask')
            if mask_has_high_trump(attack_mask, trump_suit):
                label = 'reply_high_trump'
            elif mask_has_trump(attack_mask, trump_suit):
                label = 'reply_low_trump'
            else:
                label = 'reply_nontrump'

            reply_rank = int(value(row, 'chal_first_deck0_forced_take_max_attack_rank'))
            b2_hand = value(row, 'chal_first_deck0_forced_take_defender_hand_mask')
            group_counts[label] += 1
            group_has_reply_rank[label] += int(mask_has_rank(b2_hand, reply_rank))
            group_has_trump[label] += int(mask_has_trump(b2_hand, trump_suit))
            group_force_take_option[label] += int(
                value(row, 'chal_first_deck0_forced_take_prior_attack_legal_force_take_attack_mask') > 0
            )
            group_force_high_option[label] += int(
                value(
                    row,
                    'chal_first_deck0_forced_take_prior_attack_legal_force_high_trump_cover_attack_mask',
                )
                > 0
            )
            group_chosen_force_take[label] += int(
                value(row, 'chal_first_deck0_forced_take_prior_attack_chosen_forces_take') == 1
            )
            group_chosen_force_high[label] += int(
                value(
                    row,
                    'chal_first_deck0_forced_take_prior_attack_chosen_forces_high_trump_cover',
                )
                == 1
            )
            group_prior_legal_trumps[label] += value(
                row, 'chal_first_deck0_forced_take_prior_attack_legal_trumps'
            )
            group_prior_trumps[label] += value(
                row, 'chal_first_deck0_forced_take_prior_attack_attacker_trumps'
            )
            groups[label].append(row)

    print()
    print('B4-win forced-take snapshot groups (prior attack seen)')
    print(
        'group\trows\tb2_has_reply_rank\tb2_has_trump\tforce_take_opt\tforce_high_opt\t'
        'chosen_force_take\tchosen_force_high\tprior_legal_trumps\tprior_b2_trumps'
    )
    for group in ['reply_high_trump', 'reply_low_trump', 'reply_nontrump']:
        count = group_counts[group]
        if count == 0:
            continue
        print(
            f'{group}\t{count}\t{group_has_reply_rank[group] / count:.4f}\t'
            f'{group_has_trump[group] / count:.4f}\t{group_force_take_option[group] / count:.4f}\t'
            f'{group_force_high_option[group] / count:.4f}\t'
            f'{group_chosen_force_take[group] / count:.4f}\t'
            f'{group_chosen_force_high[group] / count:.4f}\t'
            f'{group_prior_legal_trumps[group] / count:.4f}\t'
            f'{group_prior_trumps[group] / count:.4f}'
        )

    print()
    print('representative B4-win forced-take snapshots')
    print(
        'group\tseed\tgame\ttrump\tprior_b2_attack\tb4_cover\tb4_reply_attack\t'
        'b2_hand\tlegal_defense\tprior_legal_trumps\tprior_force_take\tprior_force_high\t'
        'prior_b2_trumps\tb2_has_reply_rank\tb2_has_trump'
    )
    printed = 0
    for group in ['reply_high_trump', 'reply_low_trump', 'reply_nontrump']:
        examples = [
            row for row in groups[group]
            if value(row, 'chal_first_deck0_forced_take_prior_attack_cover_is_trump') == 1
        ]
        for row in examples[: max(1, limit // 3)]:
            trump_suit = int(value(row, 'trump_suit'))
            reply_mask = value(row, 'chal_first_deck0_forced_take_attack_mask')
            reply_rank = int(value(row, 'chal_first_deck0_forced_take_max_attack_rank'))
            b2_hand = value(row, 'chal_first_deck0_forced_take_defender_hand_mask')
            prior_rank = int(value(row, 'chal_first_deck0_forced_take_prior_attack_chosen_rank'))
            prior_suit = int(value(row, 'chal_first_deck0_forced_take_prior_attack_chosen_suit'))
            cover_rank = int(value(row, 'chal_first_deck0_forced_take_prior_attack_cover_rank'))
            cover_is_trump = int(value(row, 'chal_first_deck0_forced_take_prior_attack_cover_is_trump'))
            cover = rank_suit_name(cover_rank, trump_suit) if cover_is_trump else f'{RANKS[cover_rank]}?' if cover_rank >= 0 else '--'
            print(
                f'{group}\t{row["seed"]}\t{row["game_in_pair"]}\t{SUITS[trump_suit]}\t'
                f'{rank_suit_name(prior_rank, prior_suit)}\t{cover}\t'
                f'{mask_cards(reply_mask)}\t{mask_cards(b2_hand)}\t'
                f'{mask_cards(value(row, "chal_first_deck0_forced_take_legal_defense_mask"))}\t'
                f'{int(value(row, "chal_first_deck0_forced_take_prior_attack_legal_trumps"))}\t'
                f'{mask_cards(value(row, "chal_first_deck0_forced_take_prior_attack_legal_force_take_attack_mask"))}\t'
                f'{mask_cards(value(row, "chal_first_deck0_forced_take_prior_attack_legal_force_high_trump_cover_attack_mask"))}\t'
                f'{int(value(row, "chal_first_deck0_forced_take_prior_attack_attacker_trumps"))}\t'
                f'{int(mask_has_rank(b2_hand, reply_rank))}\t{int(mask_has_trump(b2_hand, trump_suit))}'
            )
            printed += 1
            if printed >= limit:
                return


def print_small_hand_prior_option_summary(rows_by_seed: dict[str, list[dict[str, str]]]) -> None:
    rows = []
    for seed_rows in rows_by_seed.values():
        for row in seed_rows:
            if row['pair_bucket'] != 'loss':
                continue
            if row['challenger_points'] != '0.0':
                continue
            if value(row, 'chal_first_deck0_forced_take') != 1:
                continue
            if value(row, 'chal_first_deck0_forced_take_prior_attack_seen') != 1:
                continue
            rows.append(row)

    if not rows:
        return

    print()
    print('B4-win forced-take prior options by B2 prior hand size')
    print(
        'hand_max\trows\tforce_take_opt\tforce_high_opt\tchosen_force_high\t'
        'def_high_after_cover\topp_high_reply\tprior_legal_trumps\tprior_b2_trumps'
    )
    for hand_max in [2, 3, 6]:
        subset = [
            row for row in rows
            if value(row, 'chal_first_deck0_forced_take_prior_attack_attacker_hand_count') <= hand_max
        ]
        if not subset:
            continue
        n = len(subset)
        force_take = sum(
            int(value(row, 'chal_first_deck0_forced_take_prior_attack_legal_force_take_attack_mask') > 0)
            for row in subset
        )
        force_high = sum(
            int(
                value(
                    row,
                    'chal_first_deck0_forced_take_prior_attack_legal_force_high_trump_cover_attack_mask',
                )
                > 0
            )
            for row in subset
        )
        chosen_high = sum(
            int(value(row, 'chal_first_deck0_forced_take_prior_attack_chosen_forces_high_trump_cover') == 1)
            for row in subset
        )
        opp_high_reply = sum(
            int(value(row, 'chal_first_deck0_forced_take_prior_attack_opp_high_trump_attacks_after_cover') >= 1)
            for row in subset
        )
        print(
            f'<={hand_max}\t{n}\t{force_take / n:.4f}\t{force_high / n:.4f}\t'
            f'{chosen_high / n:.4f}\t'
            f'{sum(value(row, "chal_first_deck0_forced_take_prior_attack_defender_high_trumps_after_cover") for row in subset) / n:.4f}\t'
            f'{opp_high_reply / n:.4f}\t'
            f'{sum(value(row, "chal_first_deck0_forced_take_prior_attack_legal_trumps") for row in subset) / n:.4f}\t'
            f'{sum(value(row, "chal_first_deck0_forced_take_prior_attack_attacker_trumps") for row in subset) / n:.4f}'
        )

    missed = [
        row for row in rows
        if value(row, 'chal_first_deck0_forced_take_prior_attack_attacker_hand_count') <= 3
        and value(row, 'chal_first_deck0_forced_take_prior_attack_legal_force_high_trump_cover_attack_mask') > 0
        and value(row, 'chal_first_deck0_forced_take_prior_attack_chosen_forces_high_trump_cover') == 0
    ]
    print()
    print('small-hand missed force-high alternatives examples')
    print('seed\tgame\ttrump\tchosen\tforce_high_options\tlegal_attacks\tb4_high_after_cover\treply')
    for row in missed[:8]:
        trump_suit = int(value(row, 'trump_suit'))
        chosen_rank = int(value(row, 'chal_first_deck0_forced_take_prior_attack_chosen_rank'))
        chosen_suit = int(value(row, 'chal_first_deck0_forced_take_prior_attack_chosen_suit'))
        print(
            f'{row["seed"]}\t{row["game_in_pair"]}\t{SUITS[trump_suit]}\t'
            f'{rank_suit_name(chosen_rank, chosen_suit)}\t'
            f'{mask_cards(value(row, "chal_first_deck0_forced_take_prior_attack_legal_force_high_trump_cover_attack_mask"))}\t'
            f'{mask_cards(value(row, "chal_first_deck0_forced_take_prior_attack_legal_attack_mask"))}\t'
            f'{int(value(row, "chal_first_deck0_forced_take_prior_attack_defender_high_trumps_after_cover"))}\t'
            f'{mask_cards(value(row, "chal_first_deck0_forced_take_attack_mask"))}'
        )


def print_no_event_one_trump_focus(rows_by_seed: dict[str, list[dict[str, str]]]) -> None:
    rows = []
    for seed_rows in rows_by_seed.values():
        if not seed_rows or seed_rows[0]['pair_bucket'] != 'loss':
            continue
        event_games = sum(int(value(row, 'chal_first_deck0_forced_take') == 1) for row in seed_rows)
        if event_games != 0:
            continue
        for row in seed_rows:
            if row['challenger_points'] != '0.0':
                continue
            if value(row, 'chal_final_hand_count') != 2:
                continue
            if value(row, 'chal_final_trumps') != 1:
                continue
            rows.append(row)

    if not rows:
        return

    n = len(rows)
    final_high_rows = 0
    final_high_in_last_hand = 0
    final_high_legal_last = 0
    last_passed_with_final_high_legal = 0
    final_rank_self_activated = 0
    final_rank_opp_activated = 0
    final_rank_any_activated = 0
    final_high_in_prev_play_hand = 0
    final_high_legal_prev_play = 0
    final_high_legal_last_play = 0
    decision_codes: dict[int, int] = defaultdict(int)
    examples = []
    for row in rows:
        trump_suit = int(value(row, 'trump_suit'))
        final_high = high_trump_mask(value(row, 'chal_final_hand_mask'), trump_suit)
        final_rank_mask = rank_mask_from_cards(final_high)
        last_hand = value(row, 'chal_deck0_last_decision_hand_mask')
        legal_attack = value(row, 'chal_deck0_last_decision_legal_attack_mask')
        code = int(value(row, 'chal_deck0_last_decision_code'))
        decision_codes[code] += 1
        if final_high:
            final_high_rows += 1
        if final_high and mask_intersects(final_high, last_hand):
            final_high_in_last_hand += 1
        if final_high and mask_intersects(final_high, legal_attack):
            final_high_legal_last += 1
        if code == 1 and final_high and mask_intersects(final_high, legal_attack):
            last_passed_with_final_high_legal += 1
        if final_rank_mask & int(value(row, 'chal_deck0_self_played_rank_mask')):
            final_rank_self_activated += 1
        if final_rank_mask & int(value(row, 'chal_deck0_opp_played_rank_mask')):
            final_rank_opp_activated += 1
        if final_rank_mask & (
            int(value(row, 'chal_deck0_self_played_rank_mask'))
            | int(value(row, 'chal_deck0_opp_played_rank_mask'))
        ):
            final_rank_any_activated += 1
        if final_high and mask_intersects(final_high, value(row, 'chal_deck0_prev_play_hand_mask')):
            final_high_in_prev_play_hand += 1
        if final_high and mask_intersects(final_high, value(row, 'chal_deck0_prev_play_legal_attack_mask')):
            final_high_legal_prev_play += 1
        if final_high and mask_intersects(final_high, value(row, 'chal_deck0_last_play_legal_attack_mask')):
            final_high_legal_last_play += 1
        if len(examples) < 8:
            examples.append((row, final_high))

    print()
    print('no-event B4 individual losses: final hand=2, trumps=1 focus')
    print(
        'rows\tfinal_attacker_rate\tpassed_with_trump\tnontrump_with_trump\t'
        'legal_high_opts\thigh_attacks\tlast_two_pass_nt\tfinal_high_in_last_hand\t'
        'final_high_legal_last\tlast_passed_with_final_high_legal'
    )
    last_two_pass_nt = sum(
        int(
            value(row, 'chal_deck0_last_two_passes_with_trump')
            + value(row, 'chal_deck0_last_two_nontrump_with_trump') >= 1
        )
        for row in rows
    )
    print(
        f'{n}\t{sum(int(challenger_is_final_attacker(row)) for row in rows) / n:.4f}\t'
        f'{sum(value(row, "chal_deck0_attack_passes_with_trump") for row in rows) / n:.4f}\t'
        f'{sum(value(row, "chal_deck0_attack_nontrump_with_trump") for row in rows) / n:.4f}\t'
        f'{sum(value(row, "chal_deck0_legal_high_trump_attack_options") for row in rows) / n:.4f}\t'
        f'{sum(value(row, "chal_deck0_high_trump_attacks") for row in rows) / n:.4f}\t'
        f'{last_two_pass_nt / n:.4f}\t'
        f'{final_high_in_last_hand / n:.4f}\t'
        f'{final_high_legal_last / n:.4f}\t'
        f'{last_passed_with_final_high_legal / n:.4f}'
    )
    print('last_decision_code\trows\tshare')
    for code, count in sorted(decision_codes.items()):
        print(f'{code}\t{count}\t{count / n:.4f}')
    print()
    print('terminal rank activation for no-event final high trump')
    print(
        'rows\tfinal_high_rows\tself_rank_activated\topp_rank_activated\t'
        'any_rank_activated\tfinal_high_in_prev_play_hand\tfinal_high_legal_prev_play\t'
        'final_high_legal_last_play'
    )
    print(
        f'{n}\t{final_high_rows}\t{final_rank_self_activated / n:.4f}\t'
        f'{final_rank_opp_activated / n:.4f}\t{final_rank_any_activated / n:.4f}\t'
        f'{final_high_in_prev_play_hand / n:.4f}\t'
        f'{final_high_legal_prev_play / n:.4f}\t{final_high_legal_last_play / n:.4f}'
    )
    print(
        'seed\tgame\ttrump\tfinal_hand\tfinal_high_rank\tself_ranks\topp_ranks\t'
        'prev_play\tprev_legal\tlast_play\tlast_legal\tlast_decision'
    )
    for row, _ in examples:
        final_high = high_trump_mask(value(row, 'chal_final_hand_mask'), int(value(row, 'trump_suit')))
        last_rank = int(value(row, 'chal_deck0_last_play_rank'))
        last_suit = int(value(row, 'chal_deck0_last_play_suit'))
        prev_rank = int(value(row, 'chal_deck0_prev_play_rank'))
        prev_suit = int(value(row, 'chal_deck0_prev_play_suit'))
        decision_rank = int(value(row, 'chal_deck0_last_decision_chosen_rank'))
        decision_suit = int(value(row, 'chal_deck0_last_decision_chosen_suit'))
        print(
            f'{row["seed"]}\t{row["game_in_pair"]}\t{SUITS[int(value(row, "trump_suit"))]}\t'
            f'{mask_cards(value(row, "chal_final_hand_mask"))}\t'
            f'{rank_mask_names(rank_mask_from_cards(final_high))}\t'
            f'{rank_mask_names(value(row, "chal_deck0_self_played_rank_mask"))}\t'
            f'{rank_mask_names(value(row, "chal_deck0_opp_played_rank_mask"))}\t'
            f'{rank_suit_name(prev_rank, prev_suit)}\t'
            f'{mask_cards(value(row, "chal_deck0_prev_play_legal_attack_mask"))}\t'
            f'{rank_suit_name(last_rank, last_suit)}\t'
            f'{mask_cards(value(row, "chal_deck0_last_play_legal_attack_mask"))}\t'
            f'{rank_suit_name(decision_rank, decision_suit)}/'
            f'{mask_cards(value(row, "chal_deck0_last_decision_legal_attack_mask"))}\t'
            f'{int(value(row, "chal_deck0_last_decision_code"))}'
        )


def print_tiny_high_trump_window_summary(rows_by_seed: dict[str, list[dict[str, str]]]) -> None:
    rows = [row for seed_rows in rows_by_seed.values() for row in seed_rows]
    if not rows or 'chal_deck0_tiny_high_trump_opportunities' not in rows[0]:
        return

    print()
    print('terminal tiny high-trump opportunity by pair bucket')
    print(
        'bucket\trows\topp_rate\tmean_opps\tchosen_high_cond\tchosen_other_cond\t'
        'legal_nt_per_opp\tlast_opp_hand\tlast_nt_options'
    )
    for bucket in ['win', 'split', 'loss']:
        subset = [row for row in rows if row['pair_bucket'] == bucket]
        if not subset:
            continue
        opp_rows = [row for row in subset if value(row, 'chal_deck0_tiny_high_trump_opportunities') >= 1]
        opp_count = sum(value(row, 'chal_deck0_tiny_high_trump_opportunities') for row in subset)
        chosen_high = sum(value(row, 'chal_deck0_tiny_high_trump_chosen_high') for row in subset)
        chosen_other = sum(value(row, 'chal_deck0_tiny_high_trump_chosen_other') for row in subset)
        legal_nt = sum(value(row, 'chal_deck0_tiny_high_trump_legal_nontrump_options') for row in subset)
        denom = opp_count if opp_count else 1.0
        print(
            f'{bucket}\t{len(subset)}\t{len(opp_rows) / len(subset):.4f}\t'
            f'{opp_count / len(subset):.4f}\t{chosen_high / denom:.4f}\t'
            f'{chosen_other / denom:.4f}\t{legal_nt / denom:.4f}\t'
            f'{sum(value(row, "chal_deck0_tiny_high_trump_last_opponent_hand_count") for row in opp_rows) / len(opp_rows) if opp_rows else 0.0:.4f}\t'
            f'{sum(mask_popcount(value(row, "chal_deck0_tiny_high_trump_last_legal_nontrump_attack_mask")) for row in opp_rows) / len(opp_rows) if opp_rows else 0.0:.4f}'
        )

    print()
    print('terminal tiny high-trump opportunity by individual points')
    print(
        'points\trows\topp_rate\tmean_opps\tchosen_high_cond\tchosen_other_cond\t'
        'final_high_trumps\tfinal_hand'
    )
    for points in ['1.0', '0.5', '0.0']:
        subset = [row for row in rows if row['challenger_points'] == points]
        if not subset:
            continue
        opp_rows = [row for row in subset if value(row, 'chal_deck0_tiny_high_trump_opportunities') >= 1]
        opp_count = sum(value(row, 'chal_deck0_tiny_high_trump_opportunities') for row in subset)
        chosen_high = sum(value(row, 'chal_deck0_tiny_high_trump_chosen_high') for row in subset)
        chosen_other = sum(value(row, 'chal_deck0_tiny_high_trump_chosen_other') for row in subset)
        denom = opp_count if opp_count else 1.0
        print(
            f'{points}\t{len(subset)}\t{len(opp_rows) / len(subset):.4f}\t'
            f'{opp_count / len(subset):.4f}\t{chosen_high / denom:.4f}\t'
            f'{chosen_other / denom:.4f}\t'
            f'{sum(value(row, "chal_final_high_trumps") for row in opp_rows) / len(opp_rows) if opp_rows else 0.0:.4f}\t'
            f'{sum(value(row, "chal_final_hand_count") for row in opp_rows) / len(opp_rows) if opp_rows else 0.0:.4f}'
        )

    opportunity_rows = [
        row for row in rows
        if row['pair_bucket'] == 'loss'
        and row['challenger_points'] == '0.0'
        and value(row, 'chal_deck0_tiny_high_trump_opportunities') >= 1
    ]
    if not opportunity_rows:
        return

    print()
    print('B4-win individual-loss tiny high-trump opportunity examples')
    print('seed\tgame\ttrump\tfinal_hand\tlast_hand\tlegal_high\tlegal_nt\tchosen\topp_hand')
    for row in opportunity_rows[:8]:
        chosen_rank = int(value(row, 'chal_deck0_tiny_high_trump_last_chosen_rank'))
        chosen_suit = int(value(row, 'chal_deck0_tiny_high_trump_last_chosen_suit'))
        print(
            f'{row["seed"]}\t{row["game_in_pair"]}\t{SUITS[int(value(row, "trump_suit"))]}\t'
            f'{mask_cards(value(row, "chal_final_hand_mask"))}\t'
            f'{mask_cards(value(row, "chal_deck0_tiny_high_trump_last_hand_mask"))}\t'
            f'{mask_cards(value(row, "chal_deck0_tiny_high_trump_last_legal_high_trump_attack_mask"))}\t'
            f'{mask_cards(value(row, "chal_deck0_tiny_high_trump_last_legal_nontrump_attack_mask"))}\t'
            f'{rank_suit_name(chosen_rank, chosen_suit)}\t'
            f'{int(value(row, "chal_deck0_tiny_high_trump_last_opponent_hand_count"))}'
        )


def tiny_high_trump_chosen_type(row: dict[str, str]) -> str:
    chosen_rank = int(value(row, 'chal_deck0_tiny_high_trump_last_chosen_rank'))
    if chosen_rank < 0:
        return 'pass'
    if value(row, 'chal_deck0_tiny_high_trump_last_chosen_is_trump') == 0:
        return 'nontrump'
    if chosen_rank < 2:
        return 'low_trump'
    return 'high_trump'


def print_tiny_high_trump_chosen_other_strata(rows_by_seed: dict[str, list[dict[str, str]]]) -> None:
    rows = [row for seed_rows in rows_by_seed.values() for row in seed_rows]
    if not rows or 'chal_deck0_tiny_high_trump_chosen_other' not in rows[0]:
        return

    print()
    print('terminal tiny high-trump chosen-other tail by pair bucket')
    print(
        'bucket\trows\tother_rate\tmean_other\tpass_rate\tnontrump_rate\tlow_trump_rate\t'
        'opp_hand1_rate\tlegal_nt0_rate\tfinal_hand\tfinal_high_trumps'
    )
    for bucket in ['win', 'split', 'loss']:
        subset = [row for row in rows if row['pair_bucket'] == bucket]
        other_rows = [row for row in subset if value(row, 'chal_deck0_tiny_high_trump_chosen_other') >= 1]
        if not subset:
            continue
        denom = len(other_rows) if other_rows else 1
        chosen_types = [tiny_high_trump_chosen_type(row) for row in other_rows]
        print(
            f'{bucket}\t{len(subset)}\t{len(other_rows) / len(subset):.4f}\t'
            f'{sum(value(row, "chal_deck0_tiny_high_trump_chosen_other") for row in subset) / len(subset):.4f}\t'
            f'{chosen_types.count("pass") / denom:.4f}\t'
            f'{chosen_types.count("nontrump") / denom:.4f}\t'
            f'{chosen_types.count("low_trump") / denom:.4f}\t'
            f'{sum(int(value(row, "chal_deck0_tiny_high_trump_last_opponent_hand_count") == 1) for row in other_rows) / denom:.4f}\t'
            f'{sum(int(mask_popcount(value(row, "chal_deck0_tiny_high_trump_last_legal_nontrump_attack_mask")) == 0) for row in other_rows) / denom:.4f}\t'
            f'{sum(value(row, "chal_final_hand_count") for row in other_rows) / denom:.4f}\t'
            f'{sum(value(row, "chal_final_high_trumps") for row in other_rows) / denom:.4f}'
        )

    print()
    print('terminal tiny high-trump chosen-other tail by individual points')
    print(
        'points\trows\tother_rate\tpass_rate\tnontrump_rate\tlow_trump_rate\t'
        'opp_hand1_rate\tlegal_nt0_rate\tfinal_hand\tfinal_high_trumps'
    )
    for points in ['1.0', '0.5', '0.0']:
        subset = [row for row in rows if row['challenger_points'] == points]
        other_rows = [row for row in subset if value(row, 'chal_deck0_tiny_high_trump_chosen_other') >= 1]
        if not subset:
            continue
        denom = len(other_rows) if other_rows else 1
        chosen_types = [tiny_high_trump_chosen_type(row) for row in other_rows]
        print(
            f'{points}\t{len(subset)}\t{len(other_rows) / len(subset):.4f}\t'
            f'{chosen_types.count("pass") / denom:.4f}\t'
            f'{chosen_types.count("nontrump") / denom:.4f}\t'
            f'{chosen_types.count("low_trump") / denom:.4f}\t'
            f'{sum(int(value(row, "chal_deck0_tiny_high_trump_last_opponent_hand_count") == 1) for row in other_rows) / denom:.4f}\t'
            f'{sum(int(mask_popcount(value(row, "chal_deck0_tiny_high_trump_last_legal_nontrump_attack_mask")) == 0) for row in other_rows) / denom:.4f}\t'
            f'{sum(value(row, "chal_final_hand_count") for row in other_rows) / denom:.4f}\t'
            f'{sum(value(row, "chal_final_high_trumps") for row in other_rows) / denom:.4f}'
        )

    strata: dict[tuple[str, str, str, str], int] = defaultdict(int)
    for row in rows:
        if value(row, 'chal_deck0_tiny_high_trump_chosen_other') < 1:
            continue
        key = (
            row['pair_bucket'],
            hand_bucket(value(row, 'chal_final_hand_count')),
            trump_bucket(value(row, 'chal_final_high_trumps')),
            tiny_high_trump_chosen_type(row),
        )
        strata[key] += 1

    print()
    print('chosen-other final hand/high-trump strata')
    print('bucket\tfinal_hand\tfinal_high_trumps\tchosen_type\trows')
    for key, count in sorted(strata.items(), key=lambda item: (-item[1], item[0]))[:18]:
        bucket, final_hand, final_high_trumps, chosen_type = key
        print(f'{bucket}\t{final_hand}\t{final_high_trumps}\t{chosen_type}\t{count}')


def print_prior_attack_rank_distribution(rows_by_seed: dict[str, list[dict[str, str]]]) -> None:
    counts: dict[str, dict[int, int]] = defaultdict(lambda: defaultdict(int))
    cover_counts: dict[str, dict[int, int]] = defaultdict(lambda: defaultdict(int))
    for rows in rows_by_seed.values():
        for row in rows:
            if value(row, 'chal_first_deck0_forced_take') != 1:
                continue
            bucket = row['pair_bucket']
            counts[bucket][int(value(row, 'chal_first_deck0_forced_take_prior_attack_chosen_rank'))] += 1
            cover_counts[bucket][int(value(row, 'chal_first_deck0_forced_take_prior_attack_cover_rank'))] += 1

    print()
    print('prior attack chosen rank distribution (conditional on event)')
    print('bucket\trank\trows')
    for bucket in ['win', 'split', 'loss']:
        for rank, count in sorted(counts[bucket].items()):
            print(f'{bucket}\t{rank}\t{count}')

    print()
    print('prior attack cover rank distribution (conditional on event)')
    print('bucket\trank\trows')
    for bucket in ['win', 'split', 'loss']:
        for rank, count in sorted(cover_counts[bucket].items()):
            print(f'{bucket}\t{rank}\t{count}')


def main() -> None:
    args = parse_args()
    with args.features_tsv.open(newline='') as handle:
        reader = csv.DictReader(handle, delimiter='\t')
        if not reader.fieldnames:
            raise SystemExit('empty feature file')

        columns = numeric_columns(reader.fieldnames)
        by_bucket = defaultdict(Stats)
        by_points = defaultdict(Stats)
        first_events = defaultdict(EventStats)
        predicate_counts = defaultdict(lambda: defaultdict(int))
        rows_by_seed = defaultdict(list)
        total_rows = 0
        for row in reader:
            total_rows += 1
            rows_by_seed[row['seed']].append(row)
            by_bucket[row['pair_bucket']].add(row, columns)
            by_points[row['challenger_points']].add(row, columns)
            first_events[row['pair_bucket']].add(row, columns)
            for label, predicate in PREDICATES:
                if predicate(row):
                    predicate_counts[row['pair_bucket']][label] += 1

    print(f'file\t{args.features_tsv}')
    print(f'rows\t{total_rows}')
    print_bucket_summary(by_bucket, total_rows)
    print_core_means(by_bucket)
    print_predicate_rates(predicate_counts, by_bucket)
    print_top_gaps(by_bucket, columns, args.top, 'loss')
    print_top_gaps(by_bucket, columns, args.top, 'split')
    print_point_summary(by_points, total_rows)
    print_first_event_summary(first_events, by_bucket)
    print_pair_event_summary(rows_by_seed)
    print_no_event_loss_summary(rows_by_seed)
    print_forced_take_representatives(rows_by_seed)
    print_small_hand_prior_option_summary(rows_by_seed)
    print_no_event_one_trump_focus(rows_by_seed)
    print_tiny_high_trump_window_summary(rows_by_seed)
    print_tiny_high_trump_chosen_other_strata(rows_by_seed)
    print_prior_attack_rank_distribution(rows_by_seed)


if __name__ == '__main__':
    main()
