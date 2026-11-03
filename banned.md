# banned.md — AI-writing tells

Shared list for every writing bot. Each rule has an id, why it reads as AI, a fix
pattern, a weight (points off a 100 score, per hit, capped per rule), and either
`pattern:` regexes (case-insensitive, one per line) or a `detector:` name built
into the checker. Edit this file to change the gate; the checker reads it at start.

Inspired by @AISystems_hq and @Zephyr_hg ("a list with examples beats a vague
'sound human'") and @heydamir's unslopping pass.

## TG001 not-x-its-y
- why: The "It's not X, it's Y" reframe is the most-cited model tell. It sets up a straw man to knock down.
- fix: Say what the thing does. "It answers my client emails."
- weight: 12
- cap: 24
- pattern: \b(?:it|this|that)(?:'s| is) not (?:just |only |merely )?(?:a |an |the |about )?[^.,;!?\n]{1,40}[,;—–-]\s*(?:it|this|that)(?:'s| is)\b[^.!?\n]{0,60}
- pattern: \bnot (?:just |only |merely )?(?:a |an |about )?[^.,;!?\n]{1,40},? but (?:a |an |about |rather )?[^.,;!?\n]{1,40}
- pattern: \b(?:it|this|that) isn't (?:just |about )?[^.,;!?\n]{1,40}[.;—–-]\s*it's\b[^.!?\n]{0,60}
- example: It's not a chatbot, it's a coworker.

## TG002 quietly
- why: "Quietly" inflates ordinary news into a reveal.
- fix: Delete the word. If it shipped, it shipped.
- weight: 6
- cap: 12
- pattern: \bquietly\b
- example: Claude quietly shipped the best feature of the year.

## TG003 fake-deadline
- why: Invented urgency about the reader's calendar.
- fix: Say how long the setup takes. Leave the reader's calendar alone.
- weight: 8
- cap: 16
- pattern: \b(?:set|do|try|start|build|learn) (?:this|it) (?:up )?(?:before|by) (?:monday|tuesday|wednesday|thursday|friday|saturday|sunday|tomorrow|tonight|the weekend|next week)\b
- pattern: \b(?:do|try|set up|build) (?:this|it) (?:this|over the) weekend\b
- pattern: \bbefore it'?s too late\b
- pattern: \b(?:don't|do not) (?:wait|sleep on this)\b
- example: Set this up before Monday.

## TG004 crowd-address
- why: Lecturing "most people" instead of talking to the one person reading.
- fix: Talk to the one reader. Say what you do instead.
- weight: 8
- cap: 16
- pattern: \b(?:most|99%|90%) (?:of )?(?:people|founders|devs|developers|users|of you)\b(?: are)? (?:use|using|get|getting|do|doing|still|don't|won't|miss)
- pattern: \byou(?:'re| are) (?:probably )?(?:using|doing) (?:it|this|ai|claude|chatgpt|grok) wrong\b
- pattern: \beveryone (?:is|'s) sleeping on\b
- example: Most people use Claude wrong.

## TG005 like-a-pro
- why: "Can now X like a $150/hour analyst" sells a price tag instead of showing the work.
- fix: Show what it did and let the reader judge the price.
- weight: 8
- cap: 16
- pattern: \b(?:can now|now) \w+ like an? (?:pro|expert|\$?\d[\d,]*(?:/| an | per )?(?:hour|hr)\b|senior|ten-?x)
- pattern: \blike a (?:\$\d[\d,k]*(?:/hour|/hr| an hour)?|senior|pro) (?:analyst|engineer|consultant|designer|lawyer|developer)\b
- example: Claude can now research like a $150/hour analyst.

## TG006 deep-closer
- why: The little line that sounds deep restates the previous sentence as a slogan.
- fix: Delete it. The sentence before it already said it.
- weight: 7
- cap: 21
- pattern: \bthat'?s the (?:whole|entire|real) (?:game|point|trick|secret)\b
- pattern: \b(?:is|was) the part (?:everyone|most people|nobody) (?:skips|misses|ignores|talks about)\b
- pattern: \b(?:and )?that changes everything\b
- pattern: \blet that sink in\b
- pattern: \bread that again\b
- pattern: \bthe rest is history\b
- pattern: \b(?:this|that) is the way\b
- example: Setup is the part everyone skips. That's the whole game.

## TG007 triad-fragments
- why: Three one-word sentences up top ("Write. Edit. Ship.") is a rhythm models overuse.
- fix: Keep the one reason you actually believe.
- weight: 7
- cap: 14
- detector: triad_fragments
- example: Write. Edit. Ship.

## TG008 triad-list
- why: Reflexive groups of three abstract nouns or adjectives pad a sentence.
- fix: Keep the one item that matters, or name concrete things.
- weight: 4
- cap: 12
- detector: triad_list
- example: It brings speed, clarity, and confidence.

## TG009 adjective-pile
- why: Stacked hype adjectives say nothing the noun doesn't.
- fix: Name the workflow. If it's good, the name is enough.
- weight: 7
- cap: 14
- detector: adjective_pile
- example: A powerful, seamless, game-changing workflow.

## TG010 hype-words
- why: Model-favored vocabulary that people rarely use in speech.
- fix: Use the plain word, or a number.
- weight: 3
- cap: 18
- pattern: \b(?:delve|delves|delving|tapestry|testament to|game[- ]chang(?:er|ing)|revolutioni[sz]e[sd]?|unleash(?:es|ed)?|supercharge[sd]?|elevate[sd]? your|unlock(?:s|ed)? (?:the|your)|seamless(?:ly)?|robust|leverag(?:e|es|ed|ing)|cutting[- ]edge|next[- ]level|ever[- ]evolving|landscape of|realm of|navigate the complexit(?:y|ies)|paradigm shift|synerg(?:y|ies))\b
- example: Unlock the power of a seamless, cutting-edge workflow.

## TG011 sirens-arrows
- why: Siren emoji, BREAKING in capitals and arrows at the link are engagement bait.
- fix: Write the news as a normal sentence.
- weight: 8
- cap: 16
- pattern: 🚨|👇|⬇️|🧵|🔥{2,}
- pattern: \b(?:BREAKING|HUGE|MASSIVE|JUST IN)\b
- pattern: (?:^|\s)(?:→|->)\s*(?:https?://|link)
- case: sensitive
- example: 🚨 BREAKING: new model just dropped 👇

## TG012 hedges
- why: Stacked hedges make a claim sound generated and unowned.
- fix: Commit to the claim or cut it. Keep one hedge only if the doubt is real.
- weight: 3
- cap: 12
- pattern: \b(?:it'?s worth noting that|it is important to note that|it'?s important to remember|arguably|to some extent|in many ways|it could be argued|generally speaking|for what it'?s worth|i would argue)\b
- example: It's worth noting that, arguably, in many ways this helps.

## TG013 filler-opener
- why: Throat-clearing openers delay the point.
- fix: Start with the point.
- weight: 5
- cap: 10
- pattern: (?:^|\n)\s*(?:in today's (?:fast-paced )?(?:world|digital age)|let'?s dive in|let'?s be honest|here'?s the thing|picture this|imagine a world|great question|in this (?:post|thread|article),? (?:i|we)(?:'ll| will)|ever wondered|buckle up)\b
- example: Let's dive in.

## TG014 filler-closer
- why: Generic sign-offs and engagement asks read like a template.
- fix: End on the last real fact, or one specific question.
- weight: 5
- cap: 10
- pattern: \b(?:in conclusion|in summary|at the end of the day|i hope this helps|hope this helps|what do you think\?|thoughts\?|let me know in the comments|follow for more|like and retweet|the future is (?:here|now|bright))
- example: At the end of the day, the future is bright. Thoughts?

## TG015 em-dash-density
- why: Em dashes are fine once; several per 100 words is the classic model rhythm.
- fix: Use a period or a comma. Keep at most one dash per short post.
- weight: 4
- cap: 16
- detector: em_dash_density
- example: It works — fast — and it ships — today.

## TG016 rhetorical-qa
- why: Asking a question and answering it yourself ("The result? Chaos.") is a stock model move.
- fix: State the result directly.
- weight: 5
- cap: 15
- pattern: \b(?:the (?:result|answer|catch|secret|kicker|best part|twist)|why|how)\?\s+[A-Z][^.?!\n]{0,40}[.!]
- example: The result? Pure chaos.

## TG017 sycophant-opener
- why: Praise of the question or the reader before answering.
- fix: Answer.
- weight: 6
- cap: 6
- pattern: ^\s*(?:absolutely|certainly|great question|what a great|i love this question)[!,.]
- example: Absolutely! Here's how.
