# banned.md — AI-writing tells

Shared list for every writing bot. Each rule has an id, why it reads as AI, a fix
pattern, a weight (points off a 100 score, per hit, capped per rule), and either
`pattern:` regexes (case-insensitive, one per line) or a `detector:` name built
into the checker. Edit this file to change the gate; the checker reads it at start.
`rewriter:` names what the rewrite does to a hit (`delete`, `plain-word`, `dash-to-comma`,
`join-fragments`, `state-directly`, or `none`), and a pattern's `(?P<keep>...)` group is the part
a `delete` keeps.

Inspired by @AISystems_hq and @Zephyr_hg ("a list with examples beats a vague
'sound human'") and @heydamir's unslopping pass.

## TG001 not-x-its-y
- why: The "It's not X, it's Y" reframe is the most-cited model tell. It sets up a straw man to knock down.
- fix: Say what the thing does. "It answers my client emails."
- weight: 12
- cap: 24
- pattern: \b(?:it|this|that)(?:'s| is) not (?:just |only |merely )?(?:a |an |the |about )?[^.,;!?\n]{1,40}[,;—–-]\s*(?P<keep>(?:it|this|that)(?:'s| is)\b[^.!?\n]{0,60})
- pattern: (?<!\bis )(?<!\bwas )(?<!\bdid )(?<!\bdo )(?<!\bdoes )(?<!\bare )(?<!\bwere )\bnot (?:just |only |merely )?(?:a |an |about )?[^.,;!?\n]{1,40} but (?:rather )?(?P<keep>(?:a |an |about )?[^.,;!?\n]{1,40})
- pattern: \b(?:it|this|that) isn't (?:just |about )?[^.,;!?\n]{1,40}[.;—–-]\s*(?P<keep>it's\b[^.!?\n]{0,60})
- example: It's not a chatbot, it's a coworker.
- rewriter: delete

## TG002 quietly
- why: "Quietly" inflates ordinary news into a reveal.
- fix: Delete the word. If it shipped, it shipped.
- weight: 6
- cap: 12
- pattern: \bquietly\b
- example: Claude quietly shipped the best feature of the year.
- rewriter: delete

## TG003 fake-deadline
- why: Invented urgency about the reader's calendar.
- fix: Say how long the setup takes. Leave the reader's calendar alone.
- weight: 8
- cap: 16
- pattern: \b(?:set|do|try|start|build|learn) (?:this|it) (?:up )?(?:before|by) (?:monday|tuesday|wednesday|thursday|friday|saturday|sunday|tomorrow|tonight|the weekend|next week)\b
- pattern: \b(?:do|try|set up|build) (?:this|it) (?:this|over the) weekend\b
- pattern: \bbefore it'?s too late\b
- pattern: \b(?:don't|do not) (?:wait|sleep on this)(?=\s*[.!]|\s*$| (?:until|till) (?:monday|tuesday|wednesday|thursday|friday|saturday|sunday|tomorrow|next week))
- example: Set this up before Monday.
- rewriter: delete

## TG004 crowd-address
- why: Lecturing "most people" instead of talking to the one person reading.
- fix: Talk to the one reader. Say what you do instead.
- weight: 8
- cap: 16
- pattern: \b(?:most|99%|90%) (?:of )?(?:people|founders|devs|developers|users|of you)\b(?: are)?(?: still)? (?:use|using|get|getting|do|doing)\b[^.!?\n]{0,30}?\bwrong\b
- pattern: \b(?:most|99%|90%) (?:of )?(?:people|founders|devs|developers|users|of you)\b (?:miss|don't know|won't tell you) (?:this|it)\b
- pattern: \byou(?:'re| are) (?:probably )?(?:using|doing) (?:it|this|ai|claude|chatgpt|grok) wrong\b
- pattern: \beveryone (?:is|'s) sleeping on\b
- example: Most people use Claude wrong.
- rewriter: delete

## TG005 like-a-pro
- why: "Can now X like a $150/hour analyst" sells a price tag instead of showing the work.
- fix: Show what it did and let the reader judge the price.
- weight: 8
- cap: 16
- pattern: \b(?P<keep>(?:can now|now) \w+) like an? (?:pro|expert|\$?\d[\d,]*(?:/| an | per )?(?:hour|hr)|senior|ten-?x)\b(?: (?:analyst|engineer|consultant|designer|lawyer|developer)\b)?
- pattern: \blike a (?:\$\d[\d,k]*(?:/hour|/hr| an hour)?|senior|pro) (?:analyst|engineer|consultant|designer|lawyer|developer)\b
- example: Claude can now research like a $150/hour analyst.
- rewriter: delete

## TG006 deep-closer
- why: The little line that sounds deep restates the previous sentence as a slogan.
- fix: Delete it. The sentence before it already said it.
- weight: 7
- cap: 21
- pattern: \bthat'?s the (?:whole|entire|real) (?:game|point|trick|secret)\b(?=\s*[.!?…]|\s*$)
- pattern: \b(?:is|was) the part (?:everyone|most people|nobody) (?:skips|misses|ignores|talks about)\b(?=\s*[.!?…]|\s*$)
- pattern: \b(?:and )?that changes everything\b(?=\s*[.!?…]|\s*$)
- pattern: \blet that sink in\b(?=\s*[.!?…]|\s*$)
- pattern: \bread that again\b(?=\s*[.!?…]|\s*$)
- pattern: \bthe rest is history\b(?=\s*[.!?…]|\s*$)
- pattern: \b(?:this|that) is the way\b(?=\s*[.!?…]|\s*$)
- example: Setup is the part everyone skips. That's the whole game.
- rewriter: delete

## TG007 triad-fragments
- why: Three one-word sentences up top ("Write. Edit. Ship.") is a rhythm models overuse.
- fix: Keep the one reason you actually believe.
- weight: 7
- cap: 14
- detector: triad_fragments
- example: Write. Edit. Ship.
- rewriter: join-fragments

## TG008 triad-list
- why: Reflexive groups of three abstract nouns or adjectives pad a sentence.
- fix: Keep the one item that matters, or name concrete things.
- weight: 4
- cap: 12
- detector: triad_list
- example: It brings speed, clarity, and confidence.
- rewriter: none

## TG009 adjective-pile
- why: Stacked hype adjectives say nothing the noun doesn't.
- fix: Name the workflow. If it's good, the name is enough.
- weight: 7
- cap: 14
- detector: adjective_pile
- example: A powerful, seamless, game-changing workflow.
- rewriter: delete

## TG010 hype-words
- why: Model-favored vocabulary that people rarely use in speech.
- fix: Use the plain word, or a number.
- weight: 3
- cap: 18
- pattern: \b(?:delve|delves|delving|tapestry|testament to|game[- ]chang(?:er|ing)|revolutioni[sz]e[sd]?|unleash(?:es|ed)?|supercharge[sd]?|elevate[sd]? your|unlock(?:s|ed)? (?:the|your)|seamless(?:ly)?|robust(?! (?:to|against)\b)|leverag(?:e|es|ed|ing)|cutting[- ]edge|next[- ]level|ever[- ]evolving|landscape of|realm of|navigate the complexit(?:y|ies)|paradigm shift|synerg(?:y|ies))\b
- example: Unlock the power of a seamless, cutting-edge workflow.
- rewriter: plain-word

## TG011 sirens-arrows
- why: Siren emoji, BREAKING in capitals and arrows at the link are engagement bait.
- fix: Write the news as a normal sentence.
- weight: 8
- cap: 16
- pattern: 🚨|👇|⬇️|🧵|🔥{2,}
- pattern: \b(?:BREAKING|HUGE|MASSIVE)\b|\bJUST IN(?=[ \t]*[:!]|[ \t]*$)
- pattern: (?:^|\s)(?:→|->)\s*(?:https?://|link\b)
- case: sensitive
- example: 🚨 BREAKING: new model just dropped 👇
- rewriter: delete

## TG012 hedges
- why: Stacked hedges make a claim sound generated and unowned.
- fix: Commit to the claim or cut it. Keep one hedge only if the doubt is real.
- weight: 3
- cap: 12
- pattern: \b(?:it'?s worth noting that|it is important to note that|it'?s important to remember|arguably|to some extent|in many ways|it could be argued|generally speaking|for what it'?s worth|i would argue)\b
- example: It's worth noting that, arguably, in many ways this helps.
- rewriter: delete

## TG013 filler-opener
- why: Throat-clearing openers delay the point.
- fix: Start with the point.
- weight: 5
- cap: 10
- pattern: ^[ \t]*(?:in today's (?:fast-paced )?(?:world|digital age)|let'?s dive in|let'?s be honest|here'?s the thing|picture this|imagine a world|great question|in this (?:post|thread|article),? (?:i|we)(?:'ll| will)|ever wondered|buckle up)\b
- example: Let's dive in.
- rewriter: delete

## TG014 filler-closer
- why: Generic sign-offs and engagement asks read like a template.
- fix: End on the last real fact, or one specific question.
- weight: 5
- cap: 10
- pattern: \b(?:in conclusion|in summary)\b(?=,?\s+[^.!?\n]{0,20}[.!?])|\b(?:at the end of the day|i hope this helps|hope this helps|what do you think\?|thoughts\?|let me know in the comments|follow for more|like and retweet|the future is (?:here|now|bright))
- example: At the end of the day, the future is bright. Thoughts?
- rewriter: delete

## TG015 em-dash-density
- why: Em dashes are fine once; several per 100 words is the classic model rhythm.
- fix: Use a period or a comma. Keep at most one dash per short post.
- weight: 4
- cap: 16
- detector: em_dash_density
- example: It works — fast — and it ships — today.
- rewriter: dash-to-comma

## TG016 rhetorical-qa
- why: Asking a question and answering it yourself ("The result? Chaos.") is a stock model move.
- fix: State the result directly.
- weight: 5
- cap: 15
- pattern: \b(?i:the (?:result|answer|catch|secret|kicker|best part|twist))\?\s+(?P<keep>[A-Z][^.?!\n]{0,40}[.!])
- case: sensitive
- example: The result? Pure chaos.
- rewriter: state-directly

## TG017 sycophant-opener
- why: Praise of the question or the reader before answering.
- fix: Answer.
- weight: 6
- cap: 6
- pattern: ^\s*(?:absolutely|certainly|great question|what a great|i love this question)[!,.]
- example: Absolutely! Here's how.
- rewriter: delete
