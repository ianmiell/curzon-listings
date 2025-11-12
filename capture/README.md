cat curzon_tokens.json| jq -r '.bearerTokens[] | select(.key == "VistaOmnichannelComponents::browsing-domain-store") | .value' | jq . | lesst
