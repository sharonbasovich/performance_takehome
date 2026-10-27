# Anonymous exact image verification

This read-only workflow uses the public baseline publisher's accepted metadata
validation and an empty registry/Docker client configuration. It performs no login,
upload, package write, Docker unpack, GPU/model request or paid resource creation.

The source verifies all25 raw object bodies: manifest, config and23 compressed
layers. The20-minute whole verifier deadline is inside a25-minute standard public
Ubuntu job. It retains exact byte counts/hashes, each bounded raw stderr log, every
object start/partial/completion and an exclusive final receipt plus durable journal.
The artifact contains metadata/logs only; the6GB layer bodies are streamed and hashed.
An incomplete attempt remains incomplete. Runner loss can still prevent recovery;
no successful byte proof exists until its actual complete artifact is verified.

This commit changes only `registry-verification/**` and its separate verify workflow.
It does not change `registry-publisher/**` or the existing execute workflow and
therefore does not trigger a second publication. Successful authenticated publication
is separate from this anonymous byte proof and from a later anonymous Docker pull
and CPU help check. None of those substitutes for GPU inference or optimization.
