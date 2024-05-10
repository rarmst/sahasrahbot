import aiohttp
import ssl


async def create_smdash(mode="classic_mm", spoiler=False):
    async with aiohttp.ClientSession() as session:
        route = f'https://www.dashrando.net/generate/{mode}?race=1'
        if spoiler:
            route += '&spoiler=1'
        async with session.get(route, ssl=ssl.SSLContext(protocol=ssl.PROTOCOL_TLSv1_2), allow_redirects=False) as resp:
            msg = await resp.text()
            if resp.status == 307:
                return msg
            else:
                raise Exception(f"Could not generate smdash seed: {msg}")
