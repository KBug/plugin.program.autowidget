import xbmc
import xbmcgui
import xbmcvfs

import codecs
import contextlib
import io
import json
import os
import string
import time
import unicodedata
import hashlib
import glob
import math
import datetime

import six
from PIL import Image

from resources.lib.common import settings

try:
    from urllib.parse import unquote
except ImportError:
    from urlparse import unquote

try:
    translate_path = xbmcvfs.translatePath
except AttributeError:
    translate_path = xbmc.translatePath

DEFAULT_CACHE_TIME = 60 * 5

_addon_id = settings.get_addon_info("id")
_addon_data = translate_path(settings.get_addon_info("profile"))
_addon_root = translate_path(settings.get_addon_info("path"))

_art_path = os.path.join(_addon_root, "resources", "media")
_home = translate_path("special://home/")
_playback_history_path = os.path.join(_addon_data, "cache.history")

windows = {
    "programs": ["program", "script"],
    "addonbrowser": ["addon", "addons"],
    "music": ["audio", "music"],
    "pictures": ["image", "picture"],
    "videos": ["video", "videos"],
}

art_types = [
    "banner",
    "clearart",
    "clearlogo",
    "fanart",
    "icon",
    "landscape",
    "poster",
    "thumb",
]

# from https://www.rapidtables.com/web/css/css-color.html
colors = [
    "lightsalmon",
    "salmon",
    "darksalmon",
    "lightcoral",
    "indianred",
    "crimson",
    "firebrick",
    "red",
    "darkred",  # red
    "coral",
    "tomato",
    "orangered",
    "gold",
    "orange",
    "darkorange",  # orange
    "lightyellow",
    "lemonchiffon",
    "lightgoldenrodyellow",
    "papayawhip",
    "moccasin",
    "peachpuff",
    "palegoldenrod",
    "khaki",
    "darkkhaki",
    "yellow",  # yellow
    "lawngreen",
    "chartreuse",
    "limegreen",
    "lime",
    "forestgreen",
    "green",
    "darkgreen",
    "greenyellow",
    "yellowgreen",
    "springgreen",
    "mediumspringgreen",
    "lightgreen",
    "palegreen",
    "darkseagreen",
    "mediumseagreen",
    "seagreen",
    "olive",
    "darkolivegreen",
    "olivedrab",  # green
    "lightcyan",
    "cyan",
    "aqua",
    "aquamarine",
    "mediumaquamarine",
    "paleturquoise",
    "turquoise",
    "mediumturquoise",
    "darkturquoise",
    "lightseagreen",
    "cadetblue",
    "darkcyan",
    "teal",  # cyan
    "powderblue",
    "lightblue",
    "lightskyblue",
    "skyblue",
    "deepskyblue",
    "lightsteelblue",
    "dodgerblue",
    "cornflowerblue",
    "steelblue",
    "royalblue",
    "blue",
    "mediumblue",
    "darkblue",
    "navy",
    "midnightblue",
    "mediumslateblue",
    "slateblue",
    "darkslateblue",  # blue
    "lavender",
    "thistle",
    "plum",
    "violet",
    "orchid",
    "fuschia",
    "magenta",
    "mediumorchid",
    "mediumpurple",
    "blueviolet",
    "darkviolet",
    "darkorchid",
    "darkmagenta",
    "purple",
    "indigo",  # purple
    "pink",
    "lightpink",
    "hotpink",
    "deeppink",
    "palevioletred",
    "mediumvioletred",  # pink
    "white",
    "snow",
    "honeydew",
    "mintcream",
    "azure",
    "aliceblue",
    "ghostwhite",
    "whitesmoke",
    "seashell",
    "beige",
    "oldlace",
    "floralwhite",
    "ivory",
    "antiquewhite",
    "linen",
    "lavenderblush",
    "mistyrose",  # white
    "gainsboro",
    "lightgray",
    "silver",
    "darkgray",
    "gray",
    "dimgray",
    "lightslategray",
    "slategray",
    "darkslategray",
    "black",  # black
    "cornsilk",
    "blanchedalmond",
    "bisque",
    "navajowhite",
    "wheat",
    "burlywood",
    "tan",
    "rosybrown",
    "sandybrown",
    "goldenrod",
    "peru",
    "chocolate",
    "saddlebrown",
    "sienna",
    "brown",
    "maroon",
]  # brown

_startup_time = time.time()  # TODO: could get reloaded so not accurate?

_startup_time = time.time()  # TODO: could get reloaded so not accurate?


def make_holding_path(label, art):
    return {
        "jsonrpc": "2.0",
        "id": 1,
        "result": {
            "files": [
                {
                    "title": label,
                    "label": label,
                    "file": "plugin://plugin.program.autowidget/?mode=force&refresh=&reload=",
                    "art": get_art(art),
                    "filetype": "file",
                }
            ]
        },
    }


def ft(seconds):
    return str(datetime.timedelta(seconds=int(seconds)))


def log(msg, level="debug"):
    _level = xbmc.LOGDEBUG
    debug = settings.get_setting_bool("logging.debug")
    logpath = os.path.join(_addon_data, "aw_debug.log")

    if level == "debug":
        _level = xbmc.LOGDEBUG
    elif level in ["notice", "info"]:
        try:
            _level = xbmc.LOGNOTICE
        except AttributeError:
            _level = xbmc.LOGINFO
    elif level == "error":
        _level = xbmc.LOGERROR

    msg = u"{}: {}".format(_addon_id, six.text_type(msg))
    try:
        xbmc.log(msg, _level)
    except UnicodeEncodeError:
        xbmc.log(msg.encode("utf-8"), _level)
    if debug:
        debug_size = os.path.getsize(logpath) if os.path.exists(logpath) else 0
        debug_msg = u"{}  {}{}".format(time.ctime(), level.upper(), msg[25:])
        write_file(logpath, debug_msg + "\n", mode="a" if debug_size < 1048576 else "w")


def ensure_addon_data():
    if not os.path.exists(_addon_data):
        os.makedirs(_addon_data)


def wipe(folder=_addon_data):
    dialog = xbmcgui.Dialog()
    choice = dialog.yesno("AutoWidget", get_string(30044))
    del dialog

    if choice:
        for root, dirs, files in os.walk(folder):
            backup_location = translate_path(
                settings.get_setting_string("backup.location")
            )
            for name in files:
                file = os.path.join(root, name)
                if backup_location not in file:
                    os.remove(file)
            for name in dirs:
                dir = os.path.join(root, name)
                if backup_location[:-1] not in dir:
                    os.rmdir(dir)


def clear_cache(target):
    if not target:
        dialog = xbmcgui.Dialog()
        choice = dialog.yesno("AutoWidget", get_string(30118))
        del dialog

        if choice:
            for file in [i for i in os.listdir(_addon_data) if i.endswith(".cache")]:
                os.remove(os.path.join(_addon_data, file))
    else:
        os.remove(os.path.join(_addon_data, "{}.cache".format(target)))
        update_container(True)


def get_art(filename, color=None):
    art = {}
    if not color:
        color = settings.get_setting_string("ui.color")

    themed_path = os.path.join(_addon_data, color)
    if not os.path.exists(themed_path):
        os.makedirs(themed_path)

    for i in art_types:
        _i = i
        if i == "thumb":
            _i = "icon"
        path = os.path.join(_art_path, _i, "{}.png".format(filename))
        new_path = ""

        if os.path.exists(path):
            if color.lower() not in ["white", "#ffffff"]:
                new_path = os.path.join(themed_path, "{}-{}.png".format(filename, _i))
                if not os.path.exists(new_path):
                    icon = Image.open(path).convert("RGBA")
                    overlay = Image.new("RGBA", icon.size, color)
                    Image.composite(overlay, icon, icon).save(new_path)
            art[i] = clean_artwork_url(new_path if os.path.exists(new_path) else path)

    return art


def set_color(setting=False):
    dialog = xbmcgui.Dialog()
    color = settings.get_setting_string("ui.color")

    choice = dialog.yesno(
        "AutoWidget",
        get_string(30107),
        yeslabel=get_string(30108),
        nolabel=get_string(30109),
    )

    if choice:
        value = dialog.input(get_string(30110)).lower()
    else:
        value = dialog.select(
            get_string(30111),
            ["[COLOR {0}]{0}[/COLOR]".format(i) for i in colors],
            preselect=colors.index(color) if color in colors else -1,
        )
        if value > -1:
            value = colors[value]

    if value != -1:
        if value not in colors:
            if len(value) < 6:
                dialog.notification("AutoWidget", get_string(30112))
                del dialog
                return
            elif len(value) == 6 and not value.startswith("#"):
                value = "#{}".format(value)
        if setting:
            settings.set_setting_string("ui.color", value)

    del dialog
    return value


def get_active_window():
    # 'home'
    # 'dialogXXX'
    # etc...
    #
    # 'Window.Property(xmlfile)' gives full path to current window XML, this gives
    # JUST the title of the file, with no extension
    xml_file = os.path.basename(get_infolabel("Window.Property(xmlfile)").lower())[:-4]

    if xbmc.getCondVisibility("Window.IsMedia()"):
        return "media"
    elif "dialog" in xml_file:
        return "dialog"
    elif xbmc.getCondVisibility("Window.IsActive(home)"):
        return "home"
    else:
        pass


def update_container(reload=False):
    if reload:
        log("Triggering library update to reload widgets", "debug")
        xbmc.executebuiltin("UpdateLibrary(video, AutoWidget)")
    if get_active_window() == "media":
        xbmc.executebuiltin("Container.Refresh()")


def get_valid_filename(filename):
    whitelist = "-_.() {}{}".format(string.ascii_letters, string.digits)
    char_limit = 255

    filename = filename.replace(" ", "_")
    cleaned_filename = (
        unicodedata.normalize("NFKD", filename).encode("ASCII", "ignore").decode()
    )

    cleaned_filename = "".join(c for c in cleaned_filename if c in whitelist)
    if len(cleaned_filename) > char_limit:
        print(
            "Warning, filename truncated because it was over {} characters. "
            "Filenames may no longer be unique".format(char_limit)
        )

    return cleaned_filename[:char_limit]


def get_unique_id(key):
    return "{}-{}".format(get_valid_filename(six.ensure_text(key)), time.time()).lower()


def convert(input):
    if isinstance(input, dict):
        return {convert(key): convert(value) for key, value in input.items()}
    elif isinstance(input, list):
        return [convert(element) for element in input]
    elif isinstance(input, six.text_type):
        return six.ensure_text(input)

    return input


def remove_file(file):
    if os.path.exists(file):
        try:
            os.remove(file)
        except OSError as e:
            log("Could not remove {}: {}".format(file, e), level="error")


def read_file(file):
    content = None
    if os.path.exists(file):
        with io.open(os.path.join(_addon_data, file), "r", encoding="utf-8") as f:
            try:
                content = f.read()
            except Exception as e:
                log("Could not read from {}: {}".format(file, e), level="error")
    else:
        log("{} does not exist.".format(file), level="error")

    return content


def write_file(file, content, mode="w"):
    with open(file, mode) as f:
        try:
            f.write(content)
            return True
        except Exception as e:
            log("Could not write to {}: {}".format(file, e), level="error")

    return False


def read_json(file, log_file=False, default=None):
    data = None
    if os.path.exists(file):
        with codecs.open(os.path.join(_addon_data, file), "r", encoding="utf-8") as f:
            content = six.ensure_text(f.read())
            try:
                data = json.loads(content)
            except (ValueError, TypeError) as e:
                log("Could not read JSON from {}: {}".format(file, e), level="error")
                if log_file:
                    log(content, level="debug")
                return default
    else:
        log("{} does not exist.".format(file), level="error")
        return default

    return convert(data)


def write_json(file, content):
    with codecs.open(file, "w", encoding="utf-8") as f:
        try:
            json.dump(content, f, indent=4)
        except Exception as e:
            log("Could not write to {}: {}".format(file, e), level="error")


def get_string(_id, kodi=False):
    if kodi:
        return six.text_type(xbmc.getLocalizedString(_id))
    return settings.get_localized_string(_id)


def set_property(property, value, window=10000):
    xbmcgui.Window(window).setProperty(property, value)


def get_property(property, window=10000):
    return xbmcgui.Window(window).getProperty(property)


def push_queue(property, value):
    set_property(property, ",".join(get_property(property).split(",") + [value]))


def pop_queue(property):
    queue = get_property(property).split(",")
    value = queue.pop()
    set_property(property, ",".join(queue))
    return value


def clear_property(property, window=10000):
    xbmcgui.Window(window).clearProperty(property)


def get_infolabel(label):
    return xbmc.getInfoLabel(label)


def get_condition(cond):
    return xbmc.getCondVisibility(cond)


def clean_artwork_url(url):
    if url.startswith("image://") and "@" in url:
        url = url.replace(_home, "special://home/").rstrip("/")
    else:
        url = (
            unquote(url)
            .replace(_home, "special://home/")
            .replace("image://", "")
            .rstrip("/")
        )
    return url


def hash_from_cache_path(path):
    base = os.path.basename(path)
    return os.path.splitext(base)[0]


def iter_queue():
    queued = filter(os.path.isfile, glob.glob(os.path.join(_addon_data, "*.queue")))
    # TODO: sort by path instead so load plugins at the same time
    for path in sorted(queued, key=os.path.getmtime):
        yield path


def read_history(hash, create_if_missing=True):
    history_path = os.path.join(_addon_data, "{}.history".format(hash))
    if not os.path.exists(history_path):
        if create_if_missing:
            cache_data = {}
            history = cache_data.setdefault("history", [])
            widgets = cache_data.setdefault("widgets", [])
            write_json(history_path, cache_data)
        else:
            cache_data = None
    else:
        cache_data = read_json(history_path)
    return cache_data


def next_cache_queue():
    # Simple queue by creating a .queue file
    # TODO: use watchdog to use less resources
    for path in iter_queue():
        # TODO: sort by path instead so load plugins at the same time
        if not os.path.exists(path):
            # a widget update has already taken care of updating this path
            continue
        # We will let the update operation remove the item from the queue

        # TODO: need to workout if a blocking write is happen while it was queued or right now.
        # probably need a .lock file to ensure foreground calls can get priority.
        hash = hash_from_cache_path(path)
        cache_data = read_history(hash, create_if_missing=True)
        yield hash, cache_data


def push_cache_queue(path, widget_id=None):
    hash = path2hash(path)
    queue_path = os.path.join(_addon_data, "{}.queue".format(hash))
    history = read_history(hash, create_if_missing=True)  # Ensure its created
    changed = False
    if widget_id is not None and widget_id not in history["widgets"]:
        history["widgets"].append(widget_id)
        changed = True
    if history.get("path") != "path":
        history["path"] = path
        changed = True
    if changed:
        history_path = os.path.join(_addon_data, "{}.history".format(hash))
        write_json(history_path, history)

    if os.path.exists(queue_path):
        pass  # Leave original modification date so item is higher priority
    else:
        write_json(queue_path, {"hash": hash, "path": path})


def is_cache_queue(hash):
    queue_path = os.path.join(_addon_data, "{}.queue".format(hash))
    return os.path.exists(queue_path)


def remove_cache_queue(hash):
    queue_path = os.path.join(_addon_data, "{}.queue".format(hash))
    remove_file(queue_path)


def path2hash(path):
    if path is not None:
        return hashlib.sha1(six.ensure_binary(path, "utf8")).hexdigest()
    else:
        return None


def widgets_for_path(path):
    hash = path2hash(path)
    history_path = os.path.join(_addon_data, "{}.history".format(hash))
    cache_data = read_json(history_path) if os.path.exists(history_path) else None
    if cache_data is None:
        cache_data = {}
    widgets = cache_data.setdefault("widgets", [])
    return set(widgets)


def get_info_keys():
    params = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "JSONRPC.Introspect",
        "params": {
            "getmetadata": True,
            "filter": {
                "getreferences": True,
                "id": "List.Fields.Files",
                "type": "type",
            },
        },
    }
    info_keys = call_jsonrpc(params)
    return info_keys["result"]["types"]["List.Fields.Files"]["items"]["enums"]


def cache_files(path, widget_id):
    info_keys = get_info_keys()
    params = {
        "jsonrpc": "2.0",
        "method": "Files.GetDirectory",
        "params": {
            "properties": info_keys,
            "directory": path,
        },
        "id": 1,
    }
    files = call_jsonrpc(params)
    _, _, changed = cache_expiry(path, widget_id, add=files)
    return (files, changed)


def cache_expiry(path, widget_id, add=None, background=True):
    # Predict how long to cache for with a min of 5min so updates don't go in a loop
    # TODO: find better way to prevents loops so that users trying to manually refresh can do so
    # TODO: manage the cache files to remove any too old or no longer used
    # TODO: update paths on autowidget refresh based on predicted update frequency. e.g. plugins with random paths should
    # update when autowidget updates.
    hash = path2hash(path)

    cache_path = os.path.join(_addon_data, "{}.cache".format(hash))

    # Read file every time as we might be called from multiple processes
    history_path = os.path.join(_addon_data, "{}.history".format(hash))
    cache_data = read_json(history_path) if os.path.exists(history_path) else None
    if cache_data is None:
        cache_data = {}
        since_read = 0
    else:
        since_read = time.time() - last_read(hash)

    history = cache_data.setdefault("history", [])
    widgets = cache_data.setdefault("widgets", [])
    if widget_id not in widgets:
        widgets.append(widget_id)

    expiry = time.time() - 20
    contents = None
    changed = True
    size = 0

    if add is not None:
        cache_json = json.dumps(add)
        if not add or not cache_json.strip():
            result = "Invalid Write"

        elif "error" in add or not add.get("result", {}).get("files"):
            # In this case we don't want to cache a bad result
            result = "Error"
            # TODO: do we schedule a new update? or put dummy content up even if we have
            # good cached content?
        else:
            write_json(cache_path, add)
            contents = add
            size = len(cache_json)
            content_hash = path2hash(cache_json)
            changed = history[-1][1] != content_hash if history else True
            history.append((time.time(), content_hash))
            write_json(history_path, cache_data)
            # expiry = history[-1][0] + DEFAULT_CACHE_TIME
            pred_dur = predict_update_frequency(history)
            expiry = (
                history[-1][0] + pred_dur * 0.75
            )  # less than prediction to ensure pred keeps up to date
            result = "Wrote"
    else:
        # write any updated widget_ids so we know what to update when we dequeue
        # Also important as wwe use last modified of .history as accessed time
        write_json(history_path, cache_data)
        if not os.path.exists(cache_path):
            result = "Empty"
            if background:
                contents = make_holding_path(u"Loading Content...", "refresh")
                push_cache_queue(path)
        else:
            contents = read_json(cache_path, log_file=True)
            if contents is None:
                result = "Invalid Read"
                if background:
                    contents = make_holding_path("Error", "error")
                    push_cache_queue(path)
            else:
                # write any updated widget_ids so we know what to update when we dequeue
                # Also important as wwe use last modified of .history as accessed time
                write_json(history_path, cache_data)
                size = len(json.dumps(contents))
                if history:
                    expiry = history[-1][0] + predict_update_frequency(history)

                #                queue_len = len(list(iter_queue()))
                if expiry > time.time():
                    result = "Read"
                elif not background:
                    result = "Skip already updated"
                # elif queue_len > 3:
                #     # Try to give system more breathing space by returning empty cache but ensuring refresh
                #     # better way is to just do this the first X accessed after startup.
                #     # or how many accessed in the last 30s?
                #     push_cache_queue(hash)
                #     result = "Skip (queue={})".format(queue_len)
                #     contents = dict(result=dict(files=[]))
                else:
                    push_cache_queue(path)
                    result = "Read and queue"
    # TODO: some metric that tells us how long to the first and last widgets becomes visible and then get updated
    # not how to measure the time delay when when the cache is read until it appears on screen?
    # Is the first cache read always the top visibible widget?
    log(
        "{} cache {}B (exp:{}, last:{}): {} {}".format(
            result, size, ft(expiry - time.time()), ft(since_read), hash[:5], widgets
        ),
        "notice",
    )
    return expiry, contents, changed


def last_read(hash):
    # Technically this is last read or updated but we can change it to be last read Later
    # if we create another file
    path = os.path.join(_addon_data, "{}.history".format(hash))
    return os.path.getmtime(path)


def predict_update_frequency(history):
    if not history:
        return DEFAULT_CACHE_TIME
    update_count = 0
    duration = 0
    changes = []
    last_when, last = history[0]
    for when, content in history[1:]:
        update_count += 1
        if content == last:
            duration += when - last_when
        else:
            duration = (
                +(when - last_when) / 2
            )  # change could have happened any time inbetween
            changes.append((duration, update_count))
            duration = 0
            update_count = 0
        last_when = when
        last = content
    if not changes and duration:
        # drop the last part of the history that hasn't changed yet unless we have no other history to work with
        # This is an underestimate as we aren't sure when in the future it will change
        changes.append((duration, update_count))
    # TODO: the first change is potentially an underestimate too because we don't know how long it was unchanged for
    # before we started recording.

    # Now we have changes, we can do some trends on them.
    durations = [duration for duration, update_count in changes if update_count > 1]
    if not durations:
        return DEFAULT_CACHE_TIME
    med_dur = sorted(durations)[int(math.floor(len(durations) / 2)) - 1]
    avg_dur = sum(durations) / len(durations)
    # weighted by how many snapshots we took inbetween.
    # TODO: number of snapshots inbetween is really just increasing the confidence on the end time bot the duration as a whole.
    # so perhaps a better metric is the error margin of the duration? and not weighting by that completely.
    # ie durations with wide margin of error should be less important. e.g. times kodi was never turned on for months/weeks.
    weighted = sum([d * c for d, c in changes]) / sum([c for _, c in changes])
    # TODO: also try exponential decay. Older durations are less important than newer ones.
    ones = len([c for d, c in changes if c == 1]) / float(len(changes))
    # TODO: if many streaks with lots of counts then its stable and can predict
    log(
        "avg_dur {:0.0f}s, med_dur {:0.0f}s, weighted {:0.0f}s, ones {:0.2f}, all {}".format(
            avg_dur, med_dur, weighted, ones, changes
        ),
        "debug",
    )
    if ones > 0.9:
        # too unstable so no point guessing
        return DEFAULT_CACHE_TIME
    elif DEFAULT_CACHE_TIME > avg_dur / 2.0:
        # should not got less than 5min otherwise our updates go in a loop
        return DEFAULT_CACHE_TIME
    else:
        return (
            avg_dur / 2.0
        )  # we want to ensure we check more often than the actual predicted expiry


#    return DEFAULT_CACHE_TIME


def widgets_changed_by_watching(media_type):
    # Predict which widgets the skin might have that could have changed based on recently finish
    # watching something

    all_cache = filter(
        os.path.isfile, glob.glob(os.path.join(_addon_data, "*.history"))
    )

    # Simple version. Anything updated recently (since startup?)
    # priority = sorted(all_cache, key=os.path.getmtime)
    # Sort by chance of it updating
    plays = read_json(_playback_history_path, default={}).setdefault("plays", [])
    plays_for_type = [(time, t) for time, t in plays if t == media_type]
    priority = sorted(
        [
            (chance_playback_updates_widget(path, plays_for_type), path)
            for path in all_cache
        ],
        reverse=True,
    )

    for chance, path in priority:
        hash = hash_from_cache_path(path)
        last_update = os.path.getmtime(path) - _startup_time
        if last_update < 0:
            log(
                "widget not updated since startup {} {}".format(last_update, hash[:5]),
                "notice",
            )
        # elif chance < 0.3:
        #     log("chance widget changed after play {}% {}".format(chance, hash[:5]), 'notice')
        else:
            log(
                "chance widget changed after play {}% {}".format(chance, hash[:5]),
                "notice",
            )
            yield hash, path


def chance_playback_updates_widget(history_path, plays, cutoff_time=60 * 5):
    cache_data = read_json(history_path)
    history = cache_data.setdefault("history", [])
    # Complex version
    # - for each widget
    #    - come up with chance it will update after a playback
    #    - each pair of updates, is there a playback inbetween and updated with X min after playback
    #    - num playback with change / num playback with no change
    changes, non_changes, unrelated_changes = 0, 0, 0
    update = ""
    time_since_play = 0
    for play_time, media_type in plays:
        while True:
            last_update = update
            if not history:
                break
            update_time, update = history.pop(0)
            time_since_play = update_time - play_time
            # log("{} {} {} {}".format(update[:5],last_update[:5], unrelated_changes, time_since_play), 'notice')
            if time_since_play > 0:
                break
            elif update != last_update:
                unrelated_changes += 1

        if update == last_update:
            non_changes += 1
        elif (
            time_since_play > cutoff_time
        ):  # update too long after playback to be releated
            pass
        else:
            changes += 1
        # TODO: what if the previous update was a long time before playback?

    # There is probably a more statistically correct way of doing this but the idea is that
    # with few datapoints we should tend towards 0.5 probability but as we get more datapoints
    # then error goes down and rely on actual changes vs nonchanges
    # We will do a simple weighted average with 0.5 to simulate this
    # TODO: currently random widgets score higher than recently played widgets. need to score them lower
    # as they are less relevent
    log(
        "changes={}, non_changes={}, unrelated_changes={}".format(
            changes, non_changes, unrelated_changes
        ),
        "debug",
    )
    datapoints = float(changes + non_changes)
    prob = changes / float(changes + non_changes + unrelated_changes)
    unknown_weight = 4
    prob = (prob * datapoints + 0.5 * unknown_weight) / (datapoints + unknown_weight)
    return prob


def save_playback_history(media_type, playback_percentage):
    # Record in json when things got played to help predict which widgets will change after playback
    # if playback_percentage < 0.7:
    #    return
    history = read_json(_playback_history_path, default={})
    plays = history.setdefault("plays", [])
    plays.append((time.time(), media_type))
    write_json(_playback_history_path, history)


def call_builtin(action, delay=0):
    if delay:
        xbmc.sleep(delay)
    xbmc.executebuiltin(six.text_type(action))


def call_jsonrpc(request):
    call = json.dumps(request)
    response = xbmc.executeJSONRPC(call)
    return json.loads(response)


@contextlib.contextmanager
def timing(description):
    start = time.time()
    yield
    elapsed = time.time() - start

    log("{}: {}".format(description, ft(elapsed)))
