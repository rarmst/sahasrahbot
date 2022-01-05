import logging

import discord
from werkzeug.datastructures import MultiDict

from alttprbot import models
from alttprbot.alttprgen.generator import ALTTPRPreset
from alttprbot.tournament.alttpr import ALTTPRTournamentRace
from alttprbot.tournament.core import TournamentConfig
from alttprbot_discord.bot import discordbot
from alttprbot_discord.util import alttpr_discord
from pyz3r.customizer import BASE_CUSTOMIZER_PAYLOAD

class ALTTPRDEPracticeView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Generate a Practice Seed", style=discord.ButtonStyle.blurple, custom_id="sahabot:alttprde:practice", row=1)
    async def practice(self, button: discord.ui.Button, interaction: discord.Interaction):
        respmsg = await interaction.response.send_message("Generating, please wait...")
        episode_id = get_embed_field("Episode ID", interaction.message.embeds[0])
        tournament_game = await models.TournamentGames.get(episode_id=episode_id)

        seed = await alttpr_discord.ALTTPRDiscord.generate(settings=tournament_game.settings, endpoint='/api/customizer')

        await models.AuditGeneratedGames.create(
            randomizer='alttpr',
            hash_id=seed.hash,
            permalink=seed.url,
            settings=tournament_game.settings,
            gentype='preset',
            genoption=f'episode {episode_id}',
            customizer=1,
            doors=0
        )

        embed = await seed.embed(emojis=discordbot.emojis)
        await respmsg.edit_original_message(content=None, embed=embed)

class ALTTPRDETournamentGroups(ALTTPRTournamentRace):
    async def roll(self):
        self.seed = await ALTTPRPreset('open').generate(hints='off', spoilers="off", allow_quickswap=True)
        await self.create_embeds()

    async def configuration(self):
        guild = discordbot.get_guild(469300113290821632)
        return TournamentConfig(
            guild=guild,
            racetime_category='alttpr',
            racetime_goal='Beat the game',
            event_slug="alttprcd",
            audit_channel=discordbot.get_channel(473668481011679234),
            commentary_channel=discordbot.get_channel(469317757331308555),
            helper_roles=[
                guild.get_role(534030648713674765),
                guild.get_role(469300493542490112),
                guild.get_role(623071415129866240),
            ],
            lang='de',
            stream_delay=10
        )

class ALTTPRDETournamentBrackets(ALTTPRTournamentRace):
    async def roll(self):
        if self.bracket_settings is None:
            raise Exception('Missing bracket settings.  Please submit!')

        self.preset_dict = None
        self.seed = await alttpr_discord.ALTTPRDiscord.generate(settings=self.bracket_settings, endpoint='/api/customizer')
        await self.create_embeds()

    async def configuration(self):
        guild = discordbot.get_guild(469300113290821632)
        return TournamentConfig(
            guild=guild,
            racetime_category='alttpr',
            racetime_goal='Beat the game',
            event_slug="alttprcd",
            audit_channel=discordbot.get_channel(473668481011679234),
            commentary_channel=discordbot.get_channel(469317757331308555),
            helper_roles=[
                guild.get_role(534030648713674765),
                guild.get_role(469300493542490112),
                guild.get_role(623071415129866240),
            ],
            lang='de',
            stream_delay=10
        )

    @property
    def bracket_settings(self):
        if self.tournament_game:
            return self.tournament_game.settings

        return None

    @property
    def submission_form(self):
        return "submission_alttprde.html"

    async def process_submission_form(self, payload: MultiDict, submitted_by: str):
        embed = discord.Embed(
            title=f"ALTTPR DE - {self.versus}",
            description='Thank you for submitting your settings for this race!  Below is what will be played.\nIf this is incorrect, please contact a tournament admin.',
            color=discord.Colour.blue()
        )

        embed.add_field(name="Episode ID", value=self.episodeid, inline=False)
        embed.add_field(name="Event", value=self.event_slug, inline=False)
        embed.add_field(name="Game #", value=payload['game'], inline=False)

        if payload['game'] == '1':
            preset = await ALTTPRPreset('opensgl').fetch()
            settings = preset.preset_data['settings'].copy()
            embed.add_field(name="Preset", value='opensgl')
        else:
            if payload.get('item_pool') == 'sgl':
                preset = await ALTTPRPreset('sglive').fetch()
                settings = preset.preset_data['settings'].copy()
            else:
                settings = BASE_CUSTOMIZER_PAYLOAD.copy()

            settings['goal'] = payload['goal']
            settings['mode'] = payload['world_state']
            settings['weapons'] = payload['swords']
            settings['crystals']['tower'] = payload['crystals']
            settings['crystals']['ganon'] = payload['crystals']
            settings['enemizer']['boss_shuffle'] = 'full' if payload['enemizer'] in ['bosses', 'enemies_bosses'] else 'none'
            settings['enemizer']['enemy_shuffle'] = 'shuffled' if payload['enemizer'] in ['enemies', 'enemies_bosses'] else 'none'
            settings['custom']['region.wildBigKeys'] = payload['keys'] in ['bigkey', 'keysanity']
            settings['custom']['region.wildCompasses'] = payload['keys'] in ['mc', 'keysanity']
            settings['custom']['region.wildKeys'] = payload['keys'] == 'keysanity'
            settings['custom']['region.wildMaps'] = payload['keys'] in ['mc', 'keysanity']

            if payload['items'] in ['boots', 'boots_flute']:
                settings['custom']['item']['count']['PegasusBoots'] = 0
                settings['eq'].append('PegasusBoots')

            if payload['items'] in ['flute', 'boots_flute']:
                settings['custom']['item']['count']['OcarinaInactive'] = 0
                settings['eq'].append('OcarinaInactive' if payload['world_state'] == 'standard' else 'OcarinaActive')

            payload_formatted = '\n'.join([f"**{key}**: {val}" for key, val in payload.items() if not key in ['episodeid', 'game']])
            embed.add_field(name="Settings", value=payload_formatted, inline=False)

        settings['name'] = f"ALTTPRDE - {self.versus} - Game {payload['game']}"
        settings['notes'] = f"Episode {self.episodeid}<br><br>{self.versus}<br>Game {payload['game']}"

        embed.add_field(name="Submitted by", value=submitted_by, inline=False)

        await models.TournamentGames.update_or_create(episode_id=self.episodeid, defaults={'settings': settings, 'event': self.event_slug, 'game_number': payload['game']})

        if self.audit_channel:
            await self.audit_channel.send(embed=embed, view=ALTTPRDEPracticeView())

        for name, player in self.player_discords:
            if player is None:
                logging.error(f"Could not send DM to {name}")
                if self.audit_channel:
                    await self.audit_channel.send(f"@here could not send DM to {name}", allowed_mentions=discord.AllowedMentions(everyone=True), embed=embed)
                continue
            try:
                await player.send(embed=embed, view=ALTTPRDEPracticeView())
            except discord.HTTPException:
                logging.exception(f"Could not send DM to {name}")
                if self.audit_channel:
                    await self.audit_channel.send(f"@here could not send DM to {player.name}#{player.discriminator}", allowed_mentions=discord.AllowedMentions(everyone=True), embed=embed)

def get_embed_field(name: str, embed: discord.Embed) -> str:
    for field in embed.fields:
        if field.name == name:
            return field.value
    return None