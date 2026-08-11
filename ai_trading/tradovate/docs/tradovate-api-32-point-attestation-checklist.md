# Tradovate Partner API — User Self-Attestation (Full 32-Point Checklist)

> Compiled from the in-app **Connect to API / User Self Attestation** flow (items 1–32) presented to a user before generating an API key. This is distinct from, and precedes, the digital API Agreement signed afterward.

---

## Futures Trading Fundamentals & Compliance

### 1. I understand futures trading
Futures trading is different from Forex and Stock trading. There are a number of nuances unique to trading futures. You should be well aware of the additional complexities of margins, maturities, contract and tick sizes, and how to calculate your profits and losses. There are additional and specific regulations by which futures traders must comply.

### 2. I understand futures margins and Tradovate's margin policy
You understand the difference between Initial and Maintenance margins. You know the consequences of allowing an account to fall below Maintenance margin. You are aware of the most up-to-date margin prices offered by Tradovate.

### 3. I understand futures regulatory fees, exchange fees and Tradovate's commission plans
You are aware of the concept of an FCM. You understand that there is a direct relationship between your trade volume and commissions, clearing, NFA and Exchange costs. You should be aware of Tradovate's multiple available trading subscription plans.

### 4. I understand the definition of wash trades and agree to comply with all applicable regulations regarding wash trades
Traders are all subject to the same market risk. Negating your risk via wash trades places you in violation of market regulations. Initiating or participating in a wash trade, whether you did know or should have reasonably known, is a violation of Rule 534 of the market regulations.

### 5. I understand and agree to comply with regulations related to Anti Money Laundering
As part of the USA Patriot Act Title III, markets must be in compliance with anti-money laundering regulations. You should know the implications of these regulations and their impact on you or your business, and how this affects how you must track your users' identities.

### 6. I understand Exchange position limits
Aside from limits that you set via Tradovate Trader, the Exchange itself has position limits based on the current market. Be sure to understand the limitations of the exchange.

### 7. I understand the requirement to properly designate any automated orders as "Algorithmic" should they meet the requirements
In order for the user to be in compliance with exchange requirements, the `isAutomated` flag must be set for orders that were placed by an automated algorithm (as opposed to manually initiated by click, for example).

### 8. I understand sanctions which may be levied by either the Exchange or Tradovate for any service abuses
There are extensive rules and regulations that Market Regulation may impose, and each exchange has its own rulebook. Violating any of the rules will first result in attempts to resolve the violation through an approved settlement, however certain violations must be resolved in the audience of an arbitration panel and approved by the Business Conduct Committee. Know your exchange's rulebook before you trade.

### 9. I understand Tradovate's restrictions related to back month trading
The Tradovate platform allows for back month trading for most products. However, you may need to apply for a Risk Change Request depending on the number of contract months you wish to trade.

---

## Documentation, Support & Community Resources

### 10. I understand how to access Tradovate's API documentation
All of our REST API Operations are well documented and interactive. To test any REST operation, you can simply use the "Try It" feature on our API Documentation webpage.

### 11. I understand where to find coding examples related to Tradovate's API
We offer supporting projects and code examples for the JavaScript and C# languages. There are example projects for both the REST API and the WebSocket client. We have extensive documentation regarding our Custom Indicators platform, including working sample code and tutorials.

### 12. I understand how to access the Tradovate Community for community support and resources
Tradovate has a highly active and growing community. You can interact with other community members using our forums. Be sure to browse the forums when you have questions. We also offer a Community Indicators platform directly from the Tradovate dashboard, where you can browse custom indicators created by other community members, and even submit your own.

### 13. I understand that I can contact Tradovate Support only in the event there is a bug or issue with the Tradovate API
We have extensive documentation and examples regarding use of the Tradovate API. You should be certain that you understand how to use the API correctly, and rule out the possibility of human error before contacting support about a potential bug.

### 14. I understand how to check Tradovate's Service Status
You can check the status of any of our services at any time using the link. Before contacting support, check that the service you are encountering issues with is noted as active and healthy (green dot).

---

## Trading Platform, Orders & Account Values

### 15. I understand that Tradovate offers a trading front end (Tradovate Trader) that can be used for monitoring, placing, modifying and cancelling orders among other functions
Tradovate Trader, our front-end trading application, is a robustly featured enterprise-grade product and can be used to perform most trading functions you would want to perform using our API. Before using the API, take a look at Tradovate Trader — it may suit your needs all on its own.

### 16. I understand all of the order types offered by Tradovate and their limitations
You know about Market, Limit, Stop, Stop-Limit, Trailing Stop, OCO, and OSO orders, how they are submitted, and how they are filled. Every order type is a tool for a specific use case. Understanding your tools is key to developing a good trading strategy and minimizing your losses.

### 17. I understand how to calculate account performance values in real-time including but not limited to: Open and Realized P/L, Account Net Liquidating Value, Margin Requirements
Using the Tradovate Trader app will show you these values graphically, but if you plan on using the API these values will not be pre-calculated — you'll be required to do all of the calculations yourself. Our API provides just the market data, and it is up to the developer how to use it.

### 18. I understand the importance of supplying a Device ID in support of Tradovate's 2-Factor Authentication function
Two-factor Authentication is becoming an industry standard. Tradovate supports two-factor authentication, and requires that developers provide a device ID when making an authentication request.

---

## Connections, Liquidation & Risk Controls

### 19. I understand Tradovate's right to disconnect more than one connection associated with a user
You can have only a single established connection to the Tradovate API per user account. Logging on to Tradovate Trader will end your REST API/WebSocket Session and vice-versa.

### 20. I understand Tradovate's right to liquidate positions
Tradovate maintains the right to liquidate accounts that fall below certain margins. For standard contracts, if your account falls below the greater of $500 or 3.0% of the initial margin your account will be auto liquidated at your expense. Accounts not margined by 4:45PM ET are subject to liquidation.

---

## Rate Limits & API Throttling

### 21. I understand Tradovate's basic rate limits
Tradovate limits the API requests that can be made on a second, minute, and hourly basis. As soon as a cap is reached, the server will begin responding with `429: Too Many Requests`. Consumers of the API should be aware of these limitations.

### 22. I understand Tradovate's time penalty mechanism
Exceeding the request rate caps for certain novel requests will trigger the Time Penalty mechanism. In this scenario, the client must keep a special code called a ticket and re-submit it after a set period of time designated in the server response.

### 23. I understand Tradovate's right to change limits without prior notification
The existing usage caps are subject to change at any time without notice, as the Tradovate organization deems necessary and appropriate. Although this is unlikely to affect standard users, certain high-volume traders may be affected by this metric.

### 24. I understand how Tradovate throttles requests
The Tradovate API processes requests in the order they are received. However during periods of high traffic, chart data may be throttled. If you have made a high volume of chart requests, users who have made few requests in that period will have priority over your requests. This applies only to subscription requests; once a subscription is established, users can expect to receive real-time data normally.

### 25. I understand Tradovate may throttle market data depending on market status and connectivity
The Tradovate Market Data API will throttle your response data if the client application is performing poorly, or if the user's network is slow. Data for DOM, quotes, and chart updates may all be affected. When market data is throttled, multiple responses may be returned together, including combining data for multiple symbols into the same response message, and discarding pending or out-of-date data in favor of the most recent updates.

### 26. I understand Tradovate's enforced flood control rules
Tradovate maintains the right to enforce penalties that prevent users from engaging in abusive behavior. On the Tradovate level this may include the introduction of fees for exceeding certain request limits, but Exchanges may have their own additional anti-abuse policies.

---

## Permissions, Security & Third-Party Risk

### 27. I understand how to set Account Risk limits in Tradovate via the Tradovate Trader application
Tradovate Trader has a variety of simple controls that can help you manage your risk level. This includes automating loss limits and profit triggers, allowing trades of only permitted products, and setting position limits. Knowing how to utilize these tools is crucial to your trading experience.

### 28. I understand how to set the appropriate permission scope for each key which will be used for API connectivity
In order to manage what is appropriate for your user base, permission scopes can be granted on a per-API-key basis. Consider that your level of permission for personal use will differ from the level you'd grant a third party, or an unregistered user compared to a registered paying user. API key permission scope gives you control over what your application's users have the authority to do.

### 29. I understand that there is a possibility that 3rd party libraries may contain malicious code
As open source code makes up a greater portion of codebases than ever, it is important to ensure that the libraries we use in our applications are secure and tested technologies. You should be aware of known vulnerabilities in libraries utilized by your application and take the appropriate course of action to resolve and/or mitigate those vulnerabilities.

### 30. I understand the risks of using a 3rd party application or service in conjunction with my account
When choosing third party technologies, be sure that the technology you use is tested, reviewed, and safe for you and your clients. Be aware of the possibility that information associated with your account can be stolen and/or defrauded by a third party service, and do your best to defend against these circumstances by using services and apps from trusted sources.

### 31. I understand that redistribution of market data either directly or in derived works is strictly prohibited
Tradovate Users connected to the Tradovate API may not redistribute Market Data (or derivative works based on or using Market Data) to third parties in any manner.

### 32. I understand that my user has an associated simulation account that can and should be used for testing purposes
Each Live account holder at Tradovate also has unlimited access to the Simulation environment. You can choose which environment you would like to access when logging in.

---

*Note: These 32 attestations are separate from, and completed before, the digital API Agreement a user signs to finalize API access.*
