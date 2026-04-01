# Hyperstack VM Connection Details

## VM Info

| Field | Value |
|-------|-------|
| **VM Name** | `a6000-20260314-141257` |
| **VM ID** | `675003` |
| **Status** | ACTIVE / RUNNING |
| **Public IP** | `185.216.20.5` |
| **Internal IP** | `10.0.1.157` |
| **Region** | CANADA-1 |
| **OS** | Ubuntu Server 24.04 LTS R570 CUDA 12.8 with Docker |
| **GPU** | RTX-A6000 x1 |
| **CPU** | 28 cores |
| **RAM** | 58 GB |
| **Root Disk** | 100 GB |
| **Attached Volume** | `TRY_2` - 400 GB Cloud-SSD |

## SSH Connection

| Field | Value |
|-------|-------|
| **Host** | `185.216.20.5` |
| **Username** | `ubuntu` (default) or `root` |
| **Auth** | SSH Key (ed25519) |
| **Keypair** | `imac-20260314-141257` |
| **Fingerprint** | `42:7c:e7:4b:f1:13:46:3a:f0:84:1b:f0:ee:f2:9d:82` |
| **Port Randomization** | ENABLED (check Hyperstack console for randomized port) |

### Connect Command

```bash
ssh -p <RANDOMIZED_PORT> ubuntu@185.216.20.5 -i ~/.ssh/id_ed25519
```

or

```bash
ssh -p <RANDOMIZED_PORT> root@185.216.20.5 -i ~/.ssh/id_ed25519
```

> **Note:** Port randomization is enabled. The SSH port is NOT 22. Check the
> [Hyperstack Console](https://console.hyperstack.cloud) > Virtual Machines > VM 675003
> to find the randomized port number.

## API Access

| Field | Value |
|-------|-------|
| **API Key Name** | `Pandora_HyperStack_API_key` |
| **API Endpoint** | `https://infrahub-api.nexgencloud.com/v1/core/virtual-machines/675003` |

### Example API Call

```bash
curl -s -H "api_key: <YOUR_API_KEY>" \
  "https://infrahub-api.nexgencloud.com/v1/core/virtual-machines/675003"
```

## Security Rules

| Direction | Protocol | Ports | Source |
|-----------|----------|-------|--------|
| Ingress | TCP | 22 | 0.0.0.0/0 |
| Egress | Any | 1-65535 | 0.0.0.0/0 |
