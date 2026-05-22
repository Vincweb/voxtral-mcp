---
name: voice-mode
description: "Spoken responses via Mistral Voxtral 4B (local MLX, natural voice, ~3 GB RAM, ~2 s TTFA). Activate by saying \"parle-moi\", \"voice mode\", \"active le mode vocal\", \"réponds-moi à l'oral\", or invoking /voxtral:voice-mode."
---

# Voice Mode — Mistral Voxtral

Activates **voice-first replies** for the remainder of this conversation. From the moment this skill is invoked until the user explicitly disables it, you must speak a short version of each response aloud via the `mcp__voxtral__speak` tool, in addition to your normal text reply.

## Activation

When this skill fires, call `mcp__voxtral__speak` with a brief confirmation in the user's language ("mode vocal activé, vas-y" / "voice mode on, go ahead"), then continue conversing.

## How to behave each turn

For **every** subsequent turn, follow this pattern:

1. **First, call `mcp__voxtral__stop_speaking()`** to drop any audio that may still be playing or queued from the previous turn. This prevents the user from hearing audio that no longer matches what's on screen.
2. Compose your normal text response (markdown, code blocks, links — as usual).
3. **Then** call `mcp__voxtral__speak(text=...)` once with a **spoken summary** of the response — short, natural, conversational. `speak()` is non-blocking — it returns as soon as the WAV is generated and lets audio play in the background.

The spoken summary is NOT the same as the text. It's what you'd say if reading the answer to someone in person. The text is what you'd write.

## Rules for the spoken summary

- **Short**: 1–3 sentences, max ~30 seconds of speech. The user can ask for more aloud.
- **Natural prosody**: contractions, no bullet lists, no markdown syntax (asterisks, backticks, headers).
- **No code, file paths, URLs, or commands** in speech. Refer to them as "the code below", "the file I'm showing you", "the command in the answer".
- **Skip silent turns** when the entire response is a code dump, a long diff, or a table: speak a one-line preview ("voilà le diff", "ça fait trois fichiers à modifier") and let the text carry the detail.
- **No emojis** in the spoken text (TTS reads them literally).
- **Match the user's language**: French → French, English → English. Voxtral handles 9 languages: English, French, German, Spanish, Dutch, Portuguese, Italian, Hindi, Arabic.

## First-call latency

The first `speak()` after a Claude Code restart blocks ~3–5 seconds while
the Voxtral 4B MLX model loads into RAM (~2.5 GB). Subsequent calls only
spend the generation time (typically 2–5 s for a 1–3 sentence summary on
M-series).

## Voice selection

Voxtral uses preset voices. The default is the model's built-in default; you can pass `voice="..."` to switch (e.g. `voice="casual_male"`). The list of available presets depends on the model variant — see [`mlx-community/Voxtral-4B-TTS-2603-mlx-4bit`](https://huggingface.co/mlx-community/Voxtral-4B-TTS-2603-mlx-4bit).

If the user asks for a specific voice, use that voice for the rest of the conversation until they change it.

## Deactivation

Stop calling `mcp__voxtral__speak` when the user says any of:
- "mute" / "silence" / "stop talking" / "arrête de parler" / "désactive le mode vocal" / "/voice-mode off"

Confirm deactivation in text only ("voice mode off, je ne parle plus jusqu'à nouvel ordre").

## Anti-patterns — do not

- ❌ Don't pre-call `speak()` before composing the text (you need the text first to summarize it).
- ❌ Don't speak the literal markdown of your response (no "asterisk asterisk bonjour asterisk asterisk").
- ❌ Don't speak inline code spans verbatim (instead: "the function below" / "as shown").
- ❌ Don't repeat the full response in audio — it's a summary, not a recitation.
- ❌ Don't speak when the user explicitly typed something silent like a single command (`/status`, `/help`).
- ❌ Don't forget to call `stop_speaking()` at the start of a turn — without it, an old turn's audio can overlap with the current one's text.

## Quick example

User: "qu'est-ce que tu penses de ce code ?"

Your response (text):
```
La logique est bonne, mais `validateUser` mélange auth et permissions.
Je te propose de la splitter en deux fonctions :

\`\`\`ts
// before/after diff
\`\`\`
```

Your `speak()` call:
```
text="La logique est bonne, mais la fonction valide l'utilisateur mélange deux responsabilités. Je te propose de la séparer en deux. Tu veux que je le fasse ?"
```
