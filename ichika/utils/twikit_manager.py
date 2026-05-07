import logging
import json
import asyncio
from typing import Dict, Optional, List, Any

# MONKEY PATCH: Remove this block when twikit is updated to fix ON_DEMAND_FILE_REGEX
import re
_tx_mod = __import__('twikit.x_client_transaction.transaction', fromlist=['ClientTransaction'])
_tx_mod.ON_DEMAND_FILE_REGEX = re.compile(
    r""",(\d+):["']ondemand\.s["']""", flags=(re.VERBOSE | re.MULTILINE))
_tx_mod.ON_DEMAND_HASH_PATTERN = r',{}:"([0-9a-f]+)"'

async def _patched_get_indices(self, home_page_response, session, headers):
    key_byte_indices = []
    response = self.validate_response(home_page_response) or self.home_page_response
    on_demand_file_index = _tx_mod.ON_DEMAND_FILE_REGEX.search(str(response)).group(1)
    regex = re.compile(_tx_mod.ON_DEMAND_HASH_PATTERN.format(on_demand_file_index))
    filename = regex.search(str(response)).group(1)
    on_demand_file_url = f"https://abs.twimg.com/responsive-web/client-web/ondemand.s.{filename}a.js"
    on_demand_file_response = await session.request(method="GET", url=on_demand_file_url, headers=headers)
    key_byte_indices_match = _tx_mod.INDICES_REGEX.finditer(str(on_demand_file_response.text))
    for item in key_byte_indices_match:
        key_byte_indices.append(item.group(2))
    if not key_byte_indices:
        raise Exception("Couldn't get KEY_BYTE indices")
    key_byte_indices = list(map(int, key_byte_indices))
    return key_byte_indices[0], key_byte_indices[1:]

_tx_mod.ClientTransaction.get_indices = _patched_get_indices
# END MONKEY PATCH

# MONKEY PATCH: Fix KeyErrors in User.__init__
import twikit.user
_original_user_init = twikit.user.User.__init__

def _patched_user_init(self, client, data: dict) -> None:
    try:
        if 'is_blue_verified' not in data:
            data['is_blue_verified'] = False
        if 'legacy' not in data:
            data['legacy'] = {}
        
        legacy = data['legacy']
        defaults = {
            'created_at': '', 'name': '', 'screen_name': '',
            'profile_image_url_https': '', 'location': '', 'description': '',
            'pinned_tweet_ids_str': [], 'verified': False, 'possibly_sensitive': False,
            'can_dm': False, 'can_media_tag': False, 'want_retweets': False,
            'default_profile': False, 'default_profile_image': False,
            'has_custom_timelines': False, 'followers_count': 0,
            'fast_followers_count': 0, 'normal_followers_count': 0,
            'friends_count': 0, 'favourites_count': 0, 'listed_count': 0,
            'media_count': 0, 'statuses_count': 0, 'is_translator': False,
            'translator_type': '', 'withheld_in_countries': []
        }
        for k, v in defaults.items():
            if k not in legacy:
                legacy[k] = v
                
        if 'entities' not in legacy:
            legacy['entities'] = {}
        if 'description' not in legacy['entities']:
            legacy['entities']['description'] = {}
        if 'urls' not in legacy['entities']['description']:
            legacy['entities']['description']['urls'] = []
    except Exception:
        pass
    _original_user_init(self, client, data)

twikit.user.User.__init__ = _patched_user_init
# END MONKEY PATCH

from twikit import Client

logger = logging.getLogger(__name__)


class TwikitManager:
    """
    Manager for interacting with Twitter (X) using the twikit library.
    Config dict keys: 'cookie' (str or dict), optional 'proxy'.
    """

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        proxy = self.config.get('proxy')
        self.client = Client(language='en-US', proxy=proxy)

        cookie_input = self.config.get('cookie')
        if cookie_input:
            cookies = self._parse_cookie_input(cookie_input)
            self.client.set_cookies(cookies)

    def _parse_cookie_input(self, cookie_input: Any) -> Dict[str, str]:
        if isinstance(cookie_input, dict):
            return cookie_input
        cookies = {}
        if isinstance(cookie_input, str):
            for pair in cookie_input.split(';'):
                if '=' in pair:
                    try:
                        key, value = pair.strip().split('=', 1)
                        cookies[key.strip()] = value.strip()
                    except ValueError:
                        continue
        return cookies

    async def get_user_info(self, screen_name: str) -> Optional[Dict]:
        try:
            user = await self.client.get_user_by_screen_name(screen_name)
            return self._parse_user(user)
        except Exception as e:
            logger.error(f"Error fetching user info for {screen_name}: {e}")
            return None

    async def get_user_timeline(self, user_id: str, count: int = 20) -> Dict:
        try:
            tweets_result = await self.client.get_user_tweets(user_id, 'Tweets', count=count)
            tweets = list(tweets_result)
            return self._parse_timeline_tweets(tweets)
        except Exception as e:
            logger.error(f"Error fetching timeline for {user_id}: {e}")
            return {}

    async def get_tweet_detail(self, tweet_id: str) -> tuple[Optional[Dict], Optional[Dict]]:
        try:
            tweet = await self.client.get_tweet_by_id(tweet_id)
            if tweet:
                return self._parse_tweet(tweet), self._parse_user(tweet.user)
            return None, None
        except KeyError as e:
            logger.warning(f"get_tweet_by_id KeyError ({e}) for {tweet_id}, trying get_tweets_by_ids fallback")
            try:
                tweets = await self.client.get_tweets_by_ids([tweet_id])
                if tweets:
                    tweet = tweets[0]
                    return self._parse_tweet(tweet), self._parse_user(tweet.user)
                return None, None
            except Exception as e2:
                logger.error(f"Fallback also failed for {tweet_id}: {e2}")
                return None, None
        except Exception as e:
            logger.error(f"Error fetching tweet detail for {tweet_id}: {e}")
            return None, None

    def _parse_user(self, user) -> Dict:
        return {
            'id': user.id,
            'name': user.name,
            'screen_name': user.screen_name,
            'location': getattr(user, 'location', '') or '',
            'description': getattr(user, 'description', '') or '',
            'followers_count': getattr(user, 'followers_count', 0),
            'following_count': getattr(user, 'following_count', 0),
            'icon': (user.profile_image_url or '').replace('_normal', '') if getattr(user, 'profile_image_url', None) else None,
        }

    def _parse_timeline_tweets(self, tweets) -> Dict:
        timeline_data = {}
        for tweet in tweets:
            parsed = self._parse_tweet(tweet)
            if parsed and parsed.get('id'):
                timeline_data[parsed['id']] = parsed
        return timeline_data

    def _parse_tweet(self, tweet, depth=0) -> Optional[Dict]:
        if not tweet or depth > 2:
            return None

        tweet_data = {
            'tweet_type': 'default',
            'id': tweet.id,
            'text': tweet.text,
            'created_at': tweet.created_at,
            'imgs': [],
            'videos': [],
        }

        for m in (tweet.media or []):
            media_type = getattr(m, 'type', '')
            if media_type == 'photo':
                url = getattr(m, 'media_url', None)
                if url:
                    tweet_data['imgs'].append(url)
            elif media_type in ('video', 'animated_gif'):
                streams = getattr(m, 'streams', None)
                if streams:
                    mp4_streams = [s for s in streams if getattr(s, 'content_type', '') == 'video/mp4']
                    if mp4_streams:
                        best = max(mp4_streams, key=lambda s: getattr(s, 'bitrate', 0) or 0)
                        url = getattr(best, 'url', None)
                        if url:
                            tweet_data['videos'].append(url)

        try:
            retweeted = getattr(tweet, 'retweeted_tweet', None)
            if retweeted and depth < 2:
                tweet_data['tweet_type'] = 'retweet'
                rt_parsed = self._parse_tweet(retweeted, depth + 1)
                rt_user = self._parse_user(retweeted.user) if getattr(retweeted, 'user', None) else {}
                tweet_data['retweet_data'] = {'user_info': rt_user, 'data': rt_parsed or {}}
            else:
                quoted = getattr(tweet, 'quote', None)
                if quoted and depth < 2:
                    tweet_data['tweet_type'] = 'quote'
                    q_parsed = self._parse_tweet(quoted, depth + 1)
                    q_user = self._parse_user(quoted.user) if getattr(quoted, 'user', None) else {}
                    tweet_data['quote_data'] = {'user_info': q_user, 'data': q_parsed or {}}
        except Exception as e:
            logger.warning(f"Error parsing nested tweet (depth={depth}): {e}")

        return tweet_data
