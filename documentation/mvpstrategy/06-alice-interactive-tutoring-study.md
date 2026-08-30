# 06 — Alice Study: Structured Tutoring and Interactive Visual Explanations

## Purpose

This study records the product lessons inferred from an observed Alice tutoring session and translates them into implementable DeepTutor requirements. It is a product/architecture analysis based on visible behaviour, not a claim about Alice's internal implementation.

## What the observed experience demonstrates

The lesson is presented as a sequence of small learning objectives. Completed objectives are visibly marked, the current objective is highlighted, and the tutor states why it considers a step complete before moving forward.

The important product pattern is:

> Curriculum and progression are structured; AI conducts the conversation, evaluates evidence, selects a teaching action, and explains the transition.

The interface is not merely chat. It combines:

- a predefined or teacher-reviewed objective path;
- durable per-student lesson state;
- conversational teaching;
- rubric-based evidence of understanding;
- controlled progression;
- a visual progress map;
- rewards or lightweight gamification;
- the ability to ask a free-form question without losing the lesson state.

## The learning loop DeepTutor should adopt

1. Select the next eligible objective from the curriculum/prerequisite graph.
2. Establish what the learner already understands.
3. Choose an explanation modality: text, worked example, diagram, manipulable visual, animation, or guided practice.
4. Ask the learner to act or answer.
5. Evaluate the response against an objective-specific rubric.
6. If evidence is insufficient, choose a targeted hint, simpler representation, counterexample, or prerequisite.
7. If evidence is sufficient, save the evidence and mark the objective provisionally mastered.
8. Require later independent or delayed recall before reporting durable mastery.
9. Persist every meaningful transition so refresh, reconnect, or model failure cannot erase progress.

The backend, not free-form model prose, owns the authoritative session and mastery state.

## Why visual explanation is essential

Reading a generated explanation is insufficient for many learners and especially weak for procedural subjects such as Mathematics. A child often needs to see:

- what changes at each step;
- why an operation is allowed;
- which quantities remain invariant;
- how a symbolic expression relates to a concrete object or geometric model;
- what an incorrect technique changes;
- how to manipulate the representation and observe the result.

DeepTutor should therefore treat interactive visual explanation as a first-class teaching modality rather than decorative animation.

## Two different visual capabilities

### 1. Progress-path animation

The Alice-style objective path is a normal frontend component. The API returns objective order, status, prerequisite relationships, current position, and transition reason. React renders cards and SVG paths. CSS, SVG animation, or a motion library animates completion and movement.

This component does not require an LLM to draw the interface. The model may recommend the next objective, but validated backend rules update the state and the UI renders it deterministically.

Example response:

```json
{
  "lessonId": "biology-ecosystems-01",
  "currentObjectiveId": "bio-03",
  "objectives": [
    { "id": "bio-01", "title": "Ecological dependence", "status": "mastered" },
    { "id": "bio-02", "title": "Biodiversity", "status": "mastered" },
    { "id": "bio-03", "title": "Need for preservation", "status": "in_progress" }
  ],
  "transitionReason": "The learner independently explained species interdependence."
}
```

### 2. Concept and technique visualisation

This is the more important capability for Mathematics. DeepTutor needs a library of verified interactive teaching components called **visual lesson primitives**.

Examples:

| Concept family | Visual primitive |
|---|---|
| Addition/subtraction | counters, number line, regrouping blocks |
| Multiplication/division | arrays, equal groups, area model |
| Fractions | fraction bars, circles, number line, equivalence overlay |
| Place value | base-ten blocks and place-value table |
| Equations | balance scale with identical operations on both sides |
| Geometry | draggable shapes, angle measurement, transformations |
| Coordinates | interactive Cartesian grid |
| Ratios/proportions | double number line and ratio table |
| Functions | linked table, expression, and graph |
| Probability | repeatable simulation with frequency chart |

Each primitive accepts structured, validated parameters and emits learner interaction events. It is implemented and tested as product code, not invented as arbitrary JavaScript by the LLM during a child's session.

## Recommended rendering architecture

The AI acts as a lesson director:

1. The learning planner selects the objective.
2. The tutor orchestrator decides that a visual representation is appropriate.
3. The model returns a constrained visual instruction using a schema.
4. The backend validates the instruction against curriculum, age, numeric limits, and the supported component catalogue.
5. The frontend renders the named component.
6. The component reports actions such as move, group, split, plot, submit, replay, and request_hint.
7. The evaluator combines the final answer with the learner's interaction evidence.
8. The progress service saves the result and selects the next action.

Example visual instruction:

```json
{
  "component": "balance-equation",
  "version": 1,
  "objectiveId": "algebra-equations-01",
  "problem": {
    "left": ["x", 3],
    "right": [7]
  },
  "allowedActions": ["remove_both_sides", "divide_both_sides"],
  "prompt": "Remove the same amount from both sides to keep the scale balanced.",
  "successCondition": {
    "variable": "x",
    "value": 4
  }
}
```

The frontend maps `balance-equation` to a reviewed React component. Unknown components or invalid parameters are rejected and replaced with a safe fallback.

## Example: teaching 23 + 18

A weak tutor displays the written algorithm and its answer.

A visual DeepTutor lesson can:

1. Show 23 as two tens and three ones.
2. Show 18 as one ten and eight ones.
3. Let the child combine the ones.
4. Animate ten ones regrouping into one ten.
5. Move the new ten into the tens column.
6. Ask the child to state the result.
7. Give a different problem without animation to check independent transfer.

The animation is not evidence of mastery. The child's later independent solution is.

## Example: teaching x + 3 = 7

1. Render a balance with `x + 3` on the left and seven units on the right.
2. Ask the child what must be removed.
3. Only permit equivalent operations on both sides.
4. Animate the balance remaining level after removing three from each side.
5. Link the visual action to the symbolic step `x + 3 - 3 = 7 - 3`.
6. Ask the child to solve a similar equation without the balance.

This connects concrete action, mathematical rule, and symbolic notation.

## Technology choices

Use the smallest suitable renderer:

- CSS transitions and a motion library for UI/progress transitions;
- SVG for number lines, fractions, graphs, paths, and geometry;
- Canvas only for dense drawing or simulation;
- KaTeX or MathJax for mathematical notation;
- a graphing library or purpose-built SVG for coordinates and functions;
- optional authored Lottie/Rive assets for character celebration, never for mathematical correctness;
- WebGL/3D only when a validated learning need justifies the complexity.

Pre-recorded video may supplement a lesson but cannot observe the child's technique. Interactive components are more useful when the goal is diagnosis and feedback.

## AI boundaries and safety

The model may select, parameterise, and narrate a supported component. It must not:

- execute arbitrary generated HTML, SVG, JavaScript, or animation code;
- invent an unsupported mathematical rule;
- mark mastery because the child watched an animation;
- expose hidden evaluation answers in the visual payload;
- use engagement animation as a substitute for learning evidence.

All component definitions, parameter schemas, success rules, accessibility behaviour, and analytics events must be versioned and reviewed.

## Accessibility and language

Every visual must also provide:

- keyboard operation;
- screen-reader labels and text alternative;
- pause/replay and reduced-motion support;
- colour-independent state cues;
- Swedish mathematical terminology;
- optional simpler Swedish or approved additional-language narration;
- a non-visual equivalent assessment where necessary.

## MVP recommendation

The current MVP remains Biology years 7–9. Do not switch the MVP to Mathematics merely because interactive visuals are attractive.

For the Biology pilot, build the reusable architecture and only three to five visual primitives, for example:

1. objective progress path;
2. labelled-diagram interaction;
3. sequence/process animation;
4. classification or sorting interaction;
5. simple relationship or food-web explorer.

This tests whether visuals improve comprehension and completion without expanding into a full mathematics engine.

A future Mathematics pilot should start with one narrow concept family, such as fractions or introductory equations, and approximately five to eight reviewed visual components—not AI-generated universal animations.

## Data and APIs required

Store:

- visual component type and version;
- input parameters;
- linked curriculum objective;
- teaching intent;
- learner actions and timestamps;
- hint and replay usage;
- completion and error state;
- evaluation evidence;
- accessibility mode;
- model/prompt/rubric versions.

Suggested services:

- `VisualComponentCatalogue`
- `VisualInstructionValidator`
- `LessonOrchestrator`
- `InteractionEventStore`
- `MasteryEvaluator`
- `ProgressService`

## Validation metrics

Measure learning value rather than visual engagement alone:

- independent success after visual guidance;
- transfer to a different problem;
- delayed retention;
- attempts and hints before success;
- misconception correction;
- lesson completion;
- child comprehension/usability rating;
- accessibility failures;
- rendering and interaction errors;
- cost and authoring time per reusable component.

A visual should remain in the product only when it improves understanding, transfer, retention, or usability compared with a simpler explanation.

## Strategic conclusion

The defensible capability is not animation itself. Modern frontend tools can reproduce the visible Alice-style path. The deeper product value is the controlled connection among curriculum objectives, teaching strategy, verified interactive representations, learner actions, mastery evidence, durable progress, and parent reporting.

DeepTutor should build an **AI-orchestrated but product-controlled interactive lesson system**.
