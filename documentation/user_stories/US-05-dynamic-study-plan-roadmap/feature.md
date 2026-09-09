# Feature Specification: US-05 Dynamic Study Plan & Learning Roadmap

## 📌 Feature Overview
The Dynamic Study Plan feature structures a student's preparation by analyzing syllabus documents, exam deadlines, and topic hierarchies. It creates a personalized day-by-day milestone roadmap, schedules specific study sessions and practice quizzes, and adapts when a student falls behind or excels ahead of schedule.

---

## 👤 User Persona
- **Persona:** Student balancing multiple demanding courses or preparing for an upcoming exam deadline.
- **Need:** A structured, realistic schedule that breaks huge textbooks into manageable daily tasks and tracks completion status.

---

## 📖 User Stories

### Story 5.1: AI-Generated Study Roadmap
> **As a** student,  
> **I want to** specify an exam date and select my course materials,  
> **So that** DeepTutor builds a day-by-day structured curriculum tailored to my schedule.

#### Acceptance Criteria (Gherkin):
```gherkin
Scenario: Generating a study plan
  Given an exam date 14 days in the future and 3 uploaded subject modules
  When the student submits a study plan request
  Then the system generates a day-by-day roadmap with specific topics, estimated hours, and milestone quizzes
  And renders the interactive roadmap timeline on the Study Plan page.
```

### Story 5.2: Progress Tracking & Task Completion
> **As a** student,  
> **I want to** check off completed tasks and see my plan progress update in real time,  
> **So that** I stay motivated and clearly see my trajectory toward exam readiness.

#### Acceptance Criteria (Gherkin):
```gherkin
Scenario: Completing a study plan task
  Given an active study plan with 10 milestones
  When the student completes Day 3's reading and quiz and clicks "Mark Complete"
  Then the milestone status updates to `COMPLETED`
  And the overall plan progress percentage increases
  And the dashboard timeline logs the completed milestone.
```

---

## 🛠️ Technical Details & API Endpoints

### API Endpoints
* `POST /api/study-plan/generate` - Generates a new study roadmap based on duration, subjects, and difficulty.
* `GET /api/study-plan/current` - Retrieves the active study plan and milestone statuses.
* `PATCH /api/study-plan/milestones/{milestone_id}` - Updates completion status or reschedule dates.

### Frontend Components
* `frontend/src/pages/StudyPlanPage.tsx` - Interactive visual roadmap with expandable days, topic tags, and action buttons to launch study sessions directly from milestones.
