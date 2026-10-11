You write a short decision memo for Spotify's product team, using only a saved aggregate table, descriptive trend figures and a small evidence pack.

The question: at the end of this historical review window, where should the next quarter of product-improvement effort go - access/onboarding, usability, playback/performance, or billing/support?

Rules:
- Use only the facts in the input JSON. Do not invent numbers, customers, revenue, churn, causes or trends.
- Never write a digit. Refer to every number through its token exactly as given in the input, for example {C03}, {A02}, {S01} or {T04}. Code replaces each token with the saved value.
- Refer to reviews only by the review IDs listed in the evidence pack, and only in cited_reviews.
- The baseline priority of an issue is the sum of severity over its complaint and cancellation reviews (count times mean severity). Areas are sums over their issues. Recommend the area the evidence supports. If you depart from the area with the highest baseline priority, say why using the trend or robustness figures.
- Use trends_and_robustness, when present, to say whether the recommended area is growing or shrinking between the same months one year apart, whether its lead holds within the sampling intervals, and whether the independent verifier's labels give the same top area. Describe these as descriptive patterns in self-selected reviews, never as causes.
- These are self-selected public app reviews. Cancellation language is expressed intent, not observed churn. Counts describe the labeled reviews in scope, not all customers.

Return:
- recommended_area: one of the four areas.
- recommendation: two or three sentences naming the area and its top issues, with their tokens.
- rationale: three to five short points (size and severity of the top issues, trend, robustness).
- alternatives: one entry for each other area, with why it is not first, citing its tokens.
- limitations: two to four short points about what this evidence cannot show.
- cited_reviews: review IDs from the evidence pack that support the recommendation.

Return only the JSON object required by the schema.
