You write a short decision memo for Spotify's product team, using only a saved aggregate table, descriptive trend figures and a small evidence pack.

The question: at the end of this historical review window, where should the next quarter of product-improvement effort go - access/onboarding, usability, playback/performance, or billing/support?

Rules:
- Use only the facts in the input JSON. Do not invent numbers, customers, revenue, churn, causes, trends, targets or dates.
- Never write a digit anywhere in your text. Refer to every number through its token exactly as given in the input, for example {C03}, {A02}, {S01} or {T04}. Dates are tokens too: write a spike month as its month token and the two comparison periods as their earlier_period and later_period tokens, or use plain words such as "the same months one year later" or "the following year". Never type a year, a month number, a quarter number (write "next quarter"), a confidence level or a severity level yourself. Code replaces each token with the saved value and appends the token ID in parentheses automatically, so write each token only in braces (never a bare token ID or value), keep tokens in running text rather than inside your own parentheses, and put words between neighbouring tokens.
- Refer to reviews only by the review IDs listed in the evidence pack, and only in cited_reviews.
- The baseline priority of an issue is the sum of severity over its complaint and cancellation reviews (count times mean severity). Areas are sums over their issues. Recommend the area the evidence supports. If you depart from the area with the highest baseline priority, say why using the trend or robustness figures on that same metric (severity sum); a different metric alone is not a reason to depart.
- Use trends_and_robustness, when present, to say whether the recommended area is growing or shrinking between the same months one year apart, whether its lead holds within the sampling intervals, and whether the independent verifier's labels give the same top area. The verifier robustness figures use the baseline metric (row-weighted severity sum); judge the top area on that metric, and treat complaint counts as secondary. A difference in a handful of sampled reviews is noise, not a reason to depart. Describe these as descriptive patterns in self-selected reviews, never as causes.
- Read each top issue through its definition and summary. In particular, the Premium-only restrictions issue (billing.premium_only) is customers objecting that features are locked to Premium (skip limits, forced shuffle, not being able to pick, repeat or rewind songs). It sits in billing/support in the taxonomy, but it is a free-tier packaging and entitlement policy question - what the free tier includes, and how changes to it are rolled out and explained - owned with pricing and monetization. It is not a payment, charging or checkout defect: never describe it as broken billing, failed payments or a support backlog.
- These are self-selected public app reviews. Cancellation language is expressed intent, not observed churn. Counts describe the labeled reviews in scope, not all customers.
- Code appends fixed limitations to the memo (self-selected reviews rather than a customer population, no revenue or plan data, expressed intent rather than churn, star ratings not used, needs_review and quarantine counts, sample scope, golden-set agreement). Do not repeat them; your limitations should be the ones specific to this decision.

Return:
- recommended_area: one of the four areas.
- recommendation: two or three sentences naming the area, its top issues with their tokens, and what kind of work it is (for billing.premium_only: free-tier packaging and entitlement policy, not a payment defect).
- next_quarter_actions: two to four concrete actions for the next quarter, each tied to a named top issue and its tokens, saying what to change or test and which saved measure (issue complaint count, severity sum, share of complaints or trend share) should move if it works. No invented targets, owners' names or dates. At most one action may hedge the strongest alternative area.
- rationale: three to five short points (size and severity of the top issues, trend, robustness).
- what_would_change_the_call: one to three specific pieces of evidence that would change or weaken the recommendation, citing the tokens they refer to - for example the verifier's severity ordering holding on a larger verified sample, the recommended area's trend share reversing in the same months of the next year, or the spike month's lift fading back to the other months' level.
- alternatives: one entry for each other area, with why it is not first, citing its tokens.
- limitations: two to four short points about what this evidence cannot show for this decision.
- cited_reviews: review IDs from the evidence pack that support the recommendation.

Return only the JSON object required by the schema.
