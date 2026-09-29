# Acme's fleet. Add a server with one line; remove one to create a gap.
servers = {
  "web-01"    = { image = "nginx:1.21.6", owner = "alice", env = "prod", role = "web" }
  "web-02"    = { image = "nginx:1.29.1", owner = "alice", env = "prod", role = "web" }
  "cache-01"  = { image = "redis:6.0.20", owner = "bob", env = "prod", role = "cache" }
  "api-01"    = { image = "alpine:3.22", owner = "bob", env = "prod", role = "api", command = ["sleep", "infinity"] }
  "api-02"    = { image = "alpine:3.22", owner = "carol", env = "staging", role = "api", command = ["sleep", "infinity"] }
  "worker-01" = { image = "alpine:3.22", owner = "carol", env = "prod", role = "worker", command = ["sleep", "infinity"] }
  "jump-01"   = { image = "alpine:3.22", owner = "dave", env = "prod", role = "bastion", command = ["sleep", "infinity"] }
  "build-01"  = { image = "alpine:3.22", owner = "erin", env = "dev", role = "ci", command = ["sleep", "infinity"] }
}
