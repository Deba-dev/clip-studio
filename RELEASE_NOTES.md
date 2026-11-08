Clip Studio 0.7.0 finds your kills in vertical streams, makes a clip of every kill round and every death, learns any of ten games, and adds zooms, hooks and a kill counter to your clips.

## New in this version

- **Kills in vertical streams:** if you stream with your webcam stacked over the game, Clip Studio now finds the game picture inside the layout and reads it. Before, it only read plain 16:9 recordings, so vertical streams got no kill clips at all.
- **Every kill round and every death is a clip:** your kills in one round become one clip named Kill, Double kill, Triple kill, Quadra kill or Ace, and a won 1vN joins them ("1v3 clutch, triple kill"). Every kill is checked for being yours. Every death is a clip too; the ones you react to rank first.
- **The quiet parts are cut:** a slow multi-kill gets the walking between kills cut out, so an 80-second ace still plays in under a minute.
- **Ten games:** Valorant, Counter-Strike 2, BGMI, PUBG: Battlegrounds, Free Fire, Call of Duty: Mobile, Call of Duty: Warzone, Fortnite, Apex Legends and Overwatch 2. The game is picked from Settings or from the stream's title, and can be changed per stream in the review desk.
- **Teach a kill:** Valorant is read from its HUD. For the other games, pause on two of your kills and press **This frame shows my kill**, then **Find every kill**. Clip Studio learns what your kill notice looks like and finds every kill, now and on every later stream of that game.
- **Why no kills?** The review desk now says what the game reader saw on each stream, or why it found nothing.
- **Punch-in zoom:** the picture snaps in on the game at the second of each kill or death, and on your webcam when you laugh.
- **Hook text:** big text over the first seconds of a clip, typed or suggested from its title ideas.
- **Kill counter:** KILL, DOUBLE KILL, TRIPLE KILL pops up as each kill lands, named the way your game names them.
- **Search what was said:** a search box above the clip list finds any word in any clip, in Hindi or Roman letters.
- **New Settings page:** settings grouped into cards with a short explanation each, a side menu, search, game tiles, and a save bar, so nothing saves by accident (Ctrl+S saves).
- **Livelier buttons:** they ripple when clicked, spin while their job runs, and turn green when it is done.

## Install

1. Download `ClipStudio-Setup.exe` below and run it. It updates an existing install and keeps your streams and clips.
2. Windows may show "Windows protected your PC" because the app is not signed yet. Click **More info**, then **Run anyway**.

You need Windows 10 or 11. The first analysis downloads about 1.8 GB of models. Past streams are large, so a 2-hour stream can need around 15 GB of free space while it downloads.

To get kill clips from a stream analysed by an older version, open its card menu and choose **Analyze again**.

## Known limits

- Only clip streams you own or have permission to use.
- Valorant is the only game read from its HUD. The other nine need two marked kills first, and they find your kills but not your deaths.
- Teach a kill was tested on test videos, not yet on real recordings of each game. Mark another kill if it misses some.
- A multi-kill where the game's kill notice never leaves the screen between kills can count as one kill.
- Hindi captions on noisy game audio can still contain wrong words. You can edit them before export.
- The virality score is a guide for what to post first, not a promise about views.
- Without a set-up NVIDIA graphics card, captions take about 15 minutes for every 2.5 hours of stream.
- Twitch and Kick links have not been tested on real streams yet.
