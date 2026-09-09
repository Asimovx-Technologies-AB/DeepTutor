# Feature Specification: US-06 Student Dashboard & Learning Analytics

## 📌 Feature Overview
The Student Dashboard provides comprehensive visibility into learning habits, subject mastery, active study time, and recent activity. It integrates real-time active time tracking (via heartbeat pings), subject radar charts, streak counters, and recent session timelines to keep learners engaged and informed.

---

## 👤 User Persona
- **Persona:** Data-driven Student & Academic Mentor
- **Need:** Real-time visibility into study metrics, time invested per topic, retention rates, and areas requiring more focus.

---

## 📖 User Stories

### Story 6.1: Active Study Time Heartbeat Tracking
> **As a** student,  
> **I want** my actual focused study time to be recorded automatically while I am active in the study room,  
> **So that** I have an accurate record of my daily hours without counting idle tabs.

#### Acceptance Criteria (Gherkin):
```gherkin
Scenario: Tracking active study time
  Given a student interacting with the Learn Room
  When the student focuses the tab and types or reads
  Then the `useActiveTimeTracker` hook sends periodic heartbeat pings (every 30s)
  And the backend increments the user's active study time in `user_analytics`.

Scenario: User goes idle
  Given the tab is minimized or inactive for > 60s
  When no user activity is detected
  Then heartbeat pings pause to prevent false study time inflation.
```

### Story 6.2: Mastery Radar & Activity Timeline
> **As a** student,  
> **I want to** view a breakdown of my mastery across subjects and a chronological timeline of my recent sessions,  
> **So that** I can identify weak subjects and resume past sessions with one click.

#### Acceptance Criteria (Gherkin):
```gherkin
Scenario: Viewing the Dashboard
  Given an authenticated user on the Dashboard page
  When the page loads
  Then the system renders:
    1. Learning Stats Row (Total Hours, Quizzes Completed, Cards Mastered, Current Streak)
    2. Subject Mastery Radar Chart
    3. Recent Activity Timeline with direct links to continue sessions.
```

---

## 🛠️ Technical Details & API Endpoints

### API Endpoints
* `GET /api/dashboard/stats` - Returns aggregate learning statistics (hours, cards, quizzes, streaks).
* `POST /api/dashboard/heartbeat` - Receives active study time heartbeat increments.
* `GET /api/dashboard/recent-activity` - Returns timeline of recent study sessions, quiz attempts, and uploads.

### Frontend Components
* `frontend/src/components/dashboard/LearningStatsRow.tsx`
* `frontend/src/components/dashboard/RecentActivityTimeline.tsx`
* `frontend/src/hooks/useActiveTimeTracker.ts`
