import asyncio
import logging
import random
from datetime import timedelta
from typing import List

import discord
from tortoise.functions import Count

from alttprbot import models
from config import Config as c

# these should probably be in the database
QUALIFIER_MAX_SCORE = 105
QUALIFIER_MIN_SCORE = 0
MAX_POOL_IMBALANCE = 5

score_calculation_lock = asyncio.Lock()


async def calculate_async_tournament(tournament: models.AsyncTournament, only_approved: bool = False):
    """
    Iterates through each permalink for a tournament and calculates the par time for each one.
    This is intended to be run as a background task.

    If only_approved is True, only approved runs will be used to calculate the par time.

    This function is thread-safe.
    """
    async with score_calculation_lock:
        await tournament.fetch_related("permalink_pools", "permalink_pools__permalinks")
        for pool in tournament.permalink_pools:
            for permalink in pool.permalinks:
                await calculate_permalink_par(permalink, only_approved=only_approved)


async def calculate_permalink_par(permalink: models.AsyncTournamentPermalink, only_approved: bool = False):
    """
    Calculates the "par" time for a permalink by averaging the 5 fastest times.
    Write the par time to the Permalink record in the database, then write invidual scores
    """

    # don't bother scoring reattempts, we also don't want them included in the average
    query_filter = {"permalink": permalink, "status__in": ["finished", "forfeit"], "reattempted": False}

    # only score approved runs, if requested, off by default
    if only_approved:
        query_filter["review_status"] = "approved"

    races = await models.AsyncTournamentRace.filter(**query_filter).order_by()

    finished_races = [r for r in races if r.status == "finished"]

    # sort by elapsed_time attribute
    finished_races.sort(key=lambda race: race.elapsed_time)

    # calculate the average of the 5 fastest times
    if len(races) < 5:
        top_finishes = finished_races
    else:
        top_finishes = finished_races[:5]

    if len(top_finishes) == 0:
        # no runs have been submitted, so we can't calculate a par time
        # skip this permalink until we have more data
        return

    par_time = average_timedelta([race.elapsed_time for race in top_finishes])

    permalink.par_time = float(par_time.total_seconds())
    permalink.par_updated_at = discord.utils.utcnow()
    await permalink.save()

    for race in races:
        race.score = calculate_qualifier_score(par_time=par_time, elapsed_time=race.elapsed_time) if race.status == "finished" else 0
        race.score_updated_at = discord.utils.utcnow()
        await race.save()


async def get_eligible_permalink_from_pool(pool: models.AsyncTournamentPermalinkPool, user: models.Users):
    """
    Gets an eligible permalink from a pool for a user to play.
    """
    await pool.fetch_related("tournament", "permalinks")

    # get the number of times each permalink has been played
    permalink_counts = await models.AsyncTournamentRace.filter(tournament=pool.tournament, permalink__pool=pool).annotate(count=Count('permalink_id')).group_by("permalink_id").values("permalink_id", "count")
    permalink_count_dict = {item['permalink_id']: item['count'] for item in permalink_counts}
    permalink_count_dict = {p.id: permalink_count_dict.get(p.id, 0) for p in pool.permalinks if p.live_race is False}

    # get the permalinks that the user has played
    player_async_history = await models.AsyncTournamentRace.filter(user=user, tournament=pool.tournament, permalink__pool=pool).prefetch_related('permalink')

    # get the permalinks that are eligible to be played
    available_permalinks = await pool.permalinks.filter(live_race=False)
    played_permalinks = [p.permalink for p in player_async_history]
    eligible_permalinks = list(set(available_permalinks) - set(played_permalinks))

    if max(permalink_count_dict.values()) - min(permalink_count_dict.values()) > MAX_POOL_IMBALANCE:
        # pool is unbalanced, so we need to pick a permalink that has been played the least
        permalink_id = min(permalink_count_dict, key=permalink_count_dict.get)
        # ensure it's eligible to be played
        if permalink_id in [e.id for e in eligible_permalinks]:
            permalink = await models.AsyncTournamentPermalink.get(id=permalink_id)
            logging.info(f"Pool {pool.id} is unbalanced, picking permalink {permalink.id} to force.  User {user.id} has played {len(played_permalinks)} permalinks, and {len(eligible_permalinks)} are eligible.")
        else:
            # pick a random eligible permalink instead of the one we need to force, because the one we're forcing is not eligible
            permalink: models.AsyncTournamentPermalink = random.choice(eligible_permalinks)
            logging.info(f"Pool {pool.id} is unbalanced, but permalink {permalink_id} is not eligible.  Picking permalink {permalink.id} instead. User {user.id} has played {len(played_permalinks)} permalinks, and {len(eligible_permalinks)} are eligible.")
    else:
        permalink: models.AsyncTournamentPermalink = random.choice(eligible_permalinks)

    return permalink


def average_timedelta(timedelta_list: List[timedelta]) -> timedelta:
    """
    Calculates the average of a list of timedeltas
    """
    total_seconds = sum(t.total_seconds() for t in timedelta_list)
    average_seconds = total_seconds / len(timedelta_list)
    return timedelta(seconds=average_seconds)


def calculate_qualifier_score(par_time: timedelta, elapsed_time: timedelta) -> float:
    """
    Calculates a qualifier score based on the par time and elapsed time.
    The score is a percentage of the par time, with a maximum of 105% and a minimum of 0%.
    """
    return max(QUALIFIER_MIN_SCORE, min(QUALIFIER_MAX_SCORE, (2 - (elapsed_time.total_seconds() / par_time.total_seconds()))*100))


async def populate_test_data(tournament: models.AsyncTournament, participant_count: int = 1):
    """
    Populates a tournament with test data for each permalink.
    Will use fake Discord User IDs for the racers that'll be in the range of 1 to 100000, which is smaller than a real ID.
    This should only be ran in a local testing environment.
    """

    # only run this in a local testing environment
    if not c.DEBUG:
        raise Exception("This function should only be ran in a local testing environment.")

    await tournament.fetch_related("permalink_pools")

    # create specified number of fake users
    offset = random.randint(1, 1000) * 1000
    for i in range(1, participant_count + 1):
        # create a fake user, set a test_user flag to true so we can delete them later if needed
        user = await models.Users.create(
            discord_id=i + offset,
            display_name=f"Test User {i + offset}",
            test_user=True
        )
        # iterate through each pool in the tournament, using our existing algorithm to pick a permalink
        for pool in tournament.permalink_pools:
            permalink = await get_eligible_permalink_from_pool(pool, user)
            await models.AsyncTournamentRace.create(
                tournament=tournament,
                thread_id=random.randint(1, 10000000000000),
                user=user,
                thread_open_time=discord.utils.utcnow(),
                permalink=permalink,
                status="finished",
                start_time=discord.utils.utcnow(),
                end_time=discord.utils.utcnow() + timedelta(seconds=random.randint(3600000, 7200000)/1000),
            )