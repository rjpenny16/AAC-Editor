/* Communicative-function classification for topic-page phrases.
 *
 * This mirrors `phrase_function` in tdsnap/web/prompts.py line for line: the
 * server assigns a function to AI suggestions, and the client assigns one to
 * anything the user types or pastes. Both must agree, or the same phrase lands
 * in a different colored row depending on where it came from. Changing a
 * pattern here means changing it there too — tests/fixtures/phrase_function_cases.json
 * is run against both implementations so a disagreement fails CI instead of
 * shipping quietly.
 */

const PHRASE_FUNCTIONS = ["question", "comment", "positive", "negative", "personal"];

const QUESTION_PHRASE = /^(who|what|when|where|why|how|which|whose|is|are|am|was|were|do|does|did|can|could|would|will|should|may|have|has)\b/i;
const NEGATIVE_PHRASE = /\b(no|not|never|don't|doesn't|didn't|can't|cannot|won't|hate|dislike|stop|bad|boring|scary|wrong|upset|angry|sad|too loud|too busy)\b/i;
const OWNERSHIP_PHRASE = /\b(my|mine|our|ours)\b/i;
const PERSONAL_PHRASE = /^i\s+(am|was|have|had|went|saw|read|live|remember|tried|visited|played|watched|ate)\b/i;
const POSITIVE_PHRASE = /\b(love|like|enjoy|favorite|great|good|fun|awesome|amazing|excited|happy|delicious|beautiful|cool|yes|agree|please|want|best)\b/i;

function inferPhraseFunction(label, suggested = "") {
  const text = String(label || "").trim().replaceAll("’", "'");
  if (text.endsWith("?") || QUESTION_PHRASE.test(text)) return "question";
  if (NEGATIVE_PHRASE.test(text)) return "negative";
  if (OWNERSHIP_PHRASE.test(text)) return "personal";
  if (POSITIVE_PHRASE.test(text)) return "positive";
  if (PERSONAL_PHRASE.test(text)) return "personal";
  return PHRASE_FUNCTIONS.includes(suggested) && suggested !== "question" ? suggested : "comment";
}

export { inferPhraseFunction };
