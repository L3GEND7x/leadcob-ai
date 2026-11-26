# Correção do coletor após #220

Base: main 0f901f49cd248007b816622a6c0a4f89e46de6b5. O ensaio real 45862738956 leu um dos cinco sites e encontrou zero dos e-mails esperados; quatro registros reportaram robots_transport_error.

Reprodução local antes da correção: resposta gzip válida em bounded_get causa httpx.DecodingError (incorrect header check). iter_bytes já devolve bytes descomprimidos; reconstruir Response com Content-Encoding provoca uma segunda descompressão. A correção remove Content-Encoding, Content-Length e Transfer-Encoding do cabeçalho reconstruído; o tamanho é recalculado. Limites continuam aplicados ao corpo decodificado. TLS, DNS pinning, robots e restrição de redirecionamentos permanecem exigidos.

Seis testes novos exercitam gzip e deflate em stream, leitura de contatos, robots proibido, tamanho descomprimido e gzip inválido. O workflow institucional passa a executar em mudanças do transporte e do coletor, sem banco, credenciais ou mensagens. Resultado externo deverá ser registrado no PR; reprodução sintética não prova a causa de cada fonte real.

O ambiente local usa proxy SOCKS e não resolve diretamente os sites do piloto. Ensaio externo usa o runner do Actions como nos PRs #219/#220. socksio foi instalado somente no ambiente de teste local, sem alterar dependências de produção.

Nenhuma escrita em produção, integração, implantação, autorização comercial ou importação maciça foi executada. Vinculado à issue #221.
