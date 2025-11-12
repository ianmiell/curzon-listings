cat curzon_tokens.json| jq -r '.bearerTokens[] | select(.key == "VistaOmnichannelComponents::browsing-domain-store") | .value' | jq . | lesst
```
npm init -y
npm install puppeteer@latest
node capture_curzon_headless.js
```
