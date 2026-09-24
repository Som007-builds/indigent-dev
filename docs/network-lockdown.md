# Network lockdown

Indigent uses defense in depth. The automated layers are the application process
egress guard (local mode permits only configured local/private services), Qdrant's
loopback-only published port, the sandbox's `network_mode=none`, and sovereignty
telemetry counters. These layers do not replace a host firewall: firewall policy
is a manual deployment step and must be applied by the machine administrator.

Before an offline demo, while the machine is online, pull the Qdrant image, build
the sandbox image, and download all required Ollama models. Then disconnect the
machine from external networks and start only the local services.

## macOS (manual pf rule)

Create an administrator-reviewed pf anchor which blocks outbound traffic from the
dedicated account that runs Indigent, while preserving loopback traffic. Load it
with `pfctl` only after testing the rule in your environment; keep an open local
console so the rule can be reverted if necessary. Example policy content:

```pf
pass out quick on lo0 all
block drop out quick user indigent to any
```

Save it as an anchor and reference it from `/etc/pf.conf`; consult `man pf.conf`
and your macOS release documentation before enabling it. Do not apply this rule
blindly on a remotely administered machine.

## Windows (manual outbound firewall rule)

In **Windows Defender Firewall with Advanced Security**, create an **Outbound**,
**Program** rule for the exact Python executable used to run Indigent. Choose
**Block the connection**, apply it to Domain, Private, and Public profiles, and
name it `Indigent Python outbound block`. Add a more-specific allow rule for
loopback/local dependencies only if your organization requires it. Review and
enable the rule manually; no firewall command is run by this project.

## Linux (manual firewall policy)

With administrator review, allow loopback then block outbound packets from the
dedicated service account/cgroup using your distribution's approved `nftables` or
`iptables` policy. Preserve a local console and an approved rollback path before
activating rules. The exact commands vary by firewall manager and account layout,
so they must be supplied by the host administrator rather than automated here.

## Verify the offline posture

1. Start Qdrant with `docker compose up -d` and run the backend with
   `INFERENCE_MODE=local`.
2. From the backend host context, attempt `curl https://example.com`; it must
   fail. Do not use this check to make an otherwise prohibited connection in a
   production environment.
3. Confirm `GET /api/monitoring/sovereignty` reports `AIR-GAPPED`, all external
   counters are zero, `internet_access` is `BLOCKED`, and `sandbox_network` is
   `disabled`.
4. Run the sandbox network self-test; outbound connection attempts must fail and
   generate the sandbox network-blocked audit event.

If a local-mode sovereignty snapshot has any external counter above zero, treat
the result as `AIR-GAP VIOLATED`, stop the demo, and investigate before proceeding.
