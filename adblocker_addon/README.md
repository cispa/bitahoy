# Adblocker Addon
Adblocker is an addon for our bitahoy [arpjet](https://www.bitahoy.com).
It subclasses the *InterceptorAddon* and registers *TrafficFilter* to block UDP Traffic on port 53, which corresponds to most DNS traffic.
Each DNS query is upgraded to DNSoverHTTPS to a privay friendly DNS server in switzerland.
If the response contains a domain in our blocklist, the DNS Response is redirceted to localhost.


## Extendability
New devices tend to use more secure protocols for name resolution like DNSoverHTTPS already, effectively bypassing our blocking approach.
There are some methods that could be deployed to prevent this traffic as well.

## DNSoverHTTPS (DoH)
DoH uses TLS to connect to port 443 (standard TLS port) of the server.
While some TLS clients supply the hostname in clear text in the client hello message this is not the case here (tested with cloudflare).
Therefore one could craft a list of IPs to just block.
This has the major drawback that certain IPs map to many different hosts and access to all of them would be blocked. 
Some version of TLS and some clients still add the hostname field to the Client Hello, which could be used to identify a DNS.
For big server like 1.1.1.1 or 8.8.8.8 this would not break anything as they are dedicated DNS servers.
This can only be blocked and not modified as TLS certificates are verified.

## DNSoverTLS (DoT)
DoT is similar to DoH but insted of using HTTP they rely on the normal DNS protocol and just craft an encrypted envelope around it.
DoT however is only used via TCP port 853. 
Some sources claim it uses UDP but with `kdig -d @1.1.1.1 +tls-ca +tls-host=cloudflare-dns.com  example.com` it only saw TCP traffic.
Therefore it can easily be blocked, but not modified.

