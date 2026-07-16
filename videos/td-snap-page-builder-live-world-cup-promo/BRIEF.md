---
workflow: product-launch-video
flow: automation
storyboard: no
message: "Build a complete TD Snap topic page without editing every button by hand"
destination: desktop
aspect: 1920x1080
language: en-US
audience: "AAC users, parents, SLPs, and professionals"
length: 40s
angle: live-proof
narration: yes
vo_mode: restructured
captions: yes
fps: 30
---

## Intent

Create a polished new product promo showing TD Snap Page Builder and the real TD Snap
desktop app working together live. The story moves from connecting, through a World Cup
Final topic-page build and review, to the finished page appearing in TD Snap. The tone is
warm, confident, readable, and professional rather than exaggerated or salesy.

## Assets

- `README.md` — product positioning and independence language.
- `tdsnap/web/static/index.html` — real Page Builder interface and workflow copy.
- `tdsnap/web/static/app.css` — current white/navy/cobalt visual language.
- `tdsnap/web/static/app.js` — actual connect, build, preview, update, and verification flow.
- `capture/live-side-by-side.mp4` — raw recording of the disposable `AAC Editor` page set.

## Customizations

- Use the real Page Builder and TD Snap UI as the primary evidence, framed with layered panels,
  cursor choreography, precise spotlight rectangles, short zooms, and fast readable transitions.
- Build the `World Cup Final` topic with Spain-versus-Argentina AAC-friendly phrases grouped by
  Question, Comment, Positive, Negative, and Personal communicative functions.
- Generate the final warm American-English narration with ElevenLabs from the locked script.
- Derive phrase-level captions from final narration timestamps, with no caption covering active UI.
- End with `Less editing. More communicating.` and `Private. Reviewable. Local.`

## Notes

- The active TD Snap page set is the local, unsynced `AAC Editor` set. Never select or edit the
  synced/shared page sets listed in TD Snap.
- Do not use FIFA logos, match photography, broadcast footage, Figma assets, fake editor mockups,
  or any composition from the old product-promo project.
- Preserve all existing repository changes and confine new files to this project directory.
- The only online operation permitted is the requested ElevenLabs TTS call.
- The user pre-approved storyboard, design, preview, and final render; continue through delivery.
