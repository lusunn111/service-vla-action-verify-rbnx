# Architecture Image Prompt

The current README asset was generated from the prompt below and saved as
`speculative-decoding-overview-v2.png`. Reuse this prompt when regenerating or
iterating on the architecture figure.

## Web ImageGen prompt

```text
Create a beautiful, premium scientific architecture infographic for a top-tier embodied-AI open-source GitHub repository.

Canvas and visual language:
- Wide 16:9 landscape composition, at least 1920x1080.
- Clean white background with a very subtle pale-blue technical grid and generous whitespace.
- Modern 2.5D vector-like rendering, rounded module cards, crisp connectors, restrained navy-blue and cyan palette.
- Green is used only for accepted actions; orange is used only for fallback.
- Publication-ready visual hierarchy comparable to a flagship AI research repository, not a generic office flowchart.

Title, rendered exactly:
"ROBONIX SPECULATIVE DECODING"

Top lane title, rendered exactly:
"OFFLINE DRAFTER TRAINING"

Top lane flow from left to right:
"Robot Trajectories" -> "Training Samples" -> "Drafter Training" -> "Drafter Checkpoint"

Bottom lane title, rendered exactly:
"ONLINE SPECULATIVE EXECUTION"

Bottom lane flow from left to right:
"Observation + Task" -> "Drafter Candidates" -> "Target VLA Verification" -> "Confidence + Kinematics"

After "Confidence + Kinematics", draw a clear decision split. A green path labeled "ACCEPT" goes to "Action Execution" beside an elegant robot-arm pictogram. An orange path labeled "FALLBACK" loops through "Target VLA Policy" and then rejoins "Action Execution". Visually distinguish the small, fast Drafter from the large Target VLA.

Add one compact plug-in ribbon at the bottom, rendered exactly:
"KERV · Custom Drafter · Custom Verifier"

All modules and arrows must stay fully inside the frame. Use large, readable sans-serif typography. Render every supplied label verbatim. Do not add extra text, equations, code, people, company logos, watermarks, dark backgrounds, excessive gradients, duplicate modules, or cropped edges.
```

## Review checklist

- Every label is spelled exactly as provided.
- The green accept path and orange fallback loop are immediately distinguishable.
- The complete diagram remains readable when displayed at 80% README width.
- No object, arrow, or label touches or crosses the canvas boundary.

## README hero image

The decorative README hero is saved as
`docs/assets/readme/vla-action-decision-hero.webp`. It does not encode benchmark
values or robot task-success evidence.

### Built-in ImageGen regeneration prompt

```text
Use case: stylized-concept
Asset type: wide open-source project README hero banner
Primary request: Visualize speculative VLA action decision as a compact Drafter candidate tree entering a large target-model verification core, with a visible fallback loop and one ordered candidate action sequence leaving the system.
Scene/backdrop: deep navy scientific computing space with subtle orbital and network geometry
Subject: branching Drafter candidates, a dominant verification core, one fallback path, and one selected action sequence
Style/medium: premium cinematic scientific visualization, technically credible, polished 3D particles and fine data lines
Composition/framing: 2.5:1 wide banner; proposal tree on the left, target verification in the center, selected action nodes on the right; keep all important content inside safe margins
Lighting/mood: precise, calm, trustworthy, blue and cyan illumination with restrained warm accents for fallback
Color palette: dark navy, cyan, electric blue, small amber fallback accents
Constraints: no text, no logos, no people, no robot task scene, no performance numbers, no watermark, no cropped key elements
```

Generation mode: Codex built-in `imagegen`; the selected source was copied
into this repository and resized to a 1600×640 WebP for README delivery.
