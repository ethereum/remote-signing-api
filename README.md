# Ethereum remote signing APIs

**_Warning: Super fresh repo. Expect rapid iteration and breaking changes_**

API browser: [https://ethereum.github.io/remote-signing-api/](https://ethereum.github.io/remote-signing-api/)

## Outline
This repository outlines standard remote signing application programming interface (APIs) for communication between remote signers and Ethereum
validator clients.

Remote signing service allows validator clients to offload signing of validation duties (e.g  Attestations, BeaconBlocks) by managing security, slashing protection,
and key management.

The API is a REST interface, accessed via HTTP/HTTPS. This API should not be exposed directly to the public Internet and appropriate firewall rules should be
in place to restrict access only from validator clients. At the moment, only JSON is supported as return type.

The goal of this specification is to promote interoperability between various validator client implementations and remote signing services.

## Client support
| Validator Clients | Status    |
| ----------------- | --------- |
| Prysm             | Supported |
| Teku              | Supported |
| Lighthouse        | Supported |
| Nimbus            | Supported |
| Lodestar          | Supported |
| Vero              | Supported |

| Remote Signing Service | Status    |
| ---------------------- | --------- |
| Web3Signer             | Supported |

## Running API Browser Locally

To render the spec in a browser you will need an HTTP server to serve the `index.html` file.
Rendering occurs client-side in JavaScript, so no changes are required to the HTML file between
edits.

##### Python

```
python2 -m SimpleHTTPServer 8080
```

The API spec will render on [http://localhost:8080](http://localhost:8080).

##### NodeJs

```
npm install simplehttpserver -g

# OR

yarn global add simplehttpserver

simplehttpserver
```

The API spec will render on [http://localhost:8000](http://localhost:8000).

## Contributing

The API spec is linted for issues before PRs are merged.

To run the linter locally, install `spectral`:

```
npm install -g @stoplight/spectral

# OR

yarn global add @stoplight/spectral
```

and run with

```
spectral lint remote-signing-oapi.yaml
```

## Releasing

1. Create and push a tag

- Make sure `info.version` in `remote-signing-oapi.yaml` file is updated before tagging.
- CD will create github release and upload bundled spec file

2. Add release entrypoint in `index.html`

In SwaggerUIBundle configuration (inside index.html file), add another entry in "urls" field (SwaggerUI will load first item as default).
Entries should be in the following format (replace `<tag>` with the real tag name from step 1):

  ```javascript
  {url: "https://github.com/ethereum/remote-signing-api/releases/download/<tag>/remote-signing-oapi.yaml", name: "<tag>"},
    ```
