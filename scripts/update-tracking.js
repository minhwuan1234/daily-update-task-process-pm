const fs = require("fs");
const path = require("path");

const TOOL_ID = "daily-update";
const TOOL_NAME = "Daily Update Task Process PM";
const TIMEZONE = "Asia/Ho_Chi_Minh";

const ROOT = process.cwd();

const responsesPath = path.join(ROOT, "responses.json");
const membersPath = path.join(ROOT, "members.json");
const submissionsPath = path.join(ROOT, "tracking", "daily-update-submissions.json");
const summaryPath = path.join(ROOT, "tracking", "daily-update-summary.json");

function readJson(filePath, fallback) {
  try {
    if (!fs.existsSync(filePath)) return fallback;
    const raw = fs.readFileSync(filePath, "utf8").trim();
    if (!raw) return fallback;
    return JSON.parse(raw);
  } catch (error) {
    console.error(`Failed to read JSON: ${filePath}`);
    console.error(error);
    return fallback;
  }
}

function writeJson(filePath, data) {
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, JSON.stringify(data, null, 2) + "\n");
}

function getVietnamDateString(date = new Date()) {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: TIMEZONE,
    year: "numeric",
    month: "2-digit",
    day: "2-digit"
  }).format(date);
}

function normalizeMembers(membersRaw) {
  const result = {};

  for (const [memberName, memberValue] of Object.entries(membersRaw || {})) {
    if (typeof memberValue === "string") {
      result[memberValue] = {
        memberName,
        userId: memberValue
      };
    }

    if (memberValue && typeof memberValue === "object") {
      const userId =
        memberValue.open_id ||
        memberValue.openId ||
        memberValue.userId ||
        memberValue.id;

      if (userId) {
        result[userId] = {
          memberName: memberValue.name || memberName,
          userId
        };
      }
    }
  }

  return result;
}

function buildSubmissionId(date, userId, submittedAt) {
  const timestamp = new Date(submittedAt).getTime();
  return `${TOOL_ID}_${date}_${userId}_${timestamp}`;
}

function main() {
  const now = new Date();
  const today = getVietnamDateString(now);
  const submittedAt = now.toISOString();

  const responses = readJson(responsesPath, {});
  const membersRaw = readJson(membersPath, {});
  const submissions = readJson(submissionsPath, []);
  const summary = readJson(summaryPath, {});

  const membersById = normalizeMembers(membersRaw);

  const existingSubmissionIds = new Set(
    submissions.map((item) => item.submissionId)
  );

  const responseList = Array.isArray(responses.responses)
    ? responses.responses
    : Array.isArray(responses)
      ? responses
      : Object.entries(responses).map(([userId, data]) => ({ userId, ...data }));

  for (const responseData of responseList) {
    const userId = responseData.userId;
    if (!userId || typeof responseData !== "object") continue;

    const member = membersById[userId] || {};
    const memberName =
      responseData.memberName ||
      responseData.name ||
      member.memberName ||
      "Unknown";

    const actualSubmittedAt =
      responseData.submittedAt ||
      responseData.timestamp ||
      responseData.createdAt ||
      submittedAt;

    const submissionDate =
      responseData.date ||
      today;

    const submissionId = buildSubmissionId(
      submissionDate,
      userId,
      actualSubmittedAt
    );

    if (existingSubmissionIds.has(submissionId)) continue;

    const tasks = responseData.tasks || responseData.taskUpdates || [];
    const blockers =
      responseData.blockers ||
      responseData.blocker ||
      responseData.hasBlocker ||
      "";

    submissions.push({
      submissionId,
      toolId: TOOL_ID,
      toolName: TOOL_NAME,

      userId,
      memberName,

      date: submissionDate,
      submittedAt: actualSubmittedAt,
      timezone: TIMEZONE,

      tasksAssigned: Array.isArray(tasks) ? tasks.length : null,
      tasksUpdated: Array.isArray(tasks)
        ? tasks.filter((task) => {
            if (!task) return false;
            if (typeof task === "string") return task.trim().length > 0;
            return Object.values(task).some((value) => String(value || "").trim());
          }).length
        : null,

      hasBlocker: Boolean(
        typeof blockers === "boolean"
          ? blockers
          : String(blockers || "").trim()
      ),

      progressStatus: "submitted",
      source: "github-actions",
      responseFile: "responses.json"
    });

    existingSubmissionIds.add(submissionId);
  }

  const allMemberIds = Object.keys(membersById);
  const submittedToday = submissions.filter((item) => item.date === today);
  const submittedTodayIds = new Set(submittedToday.map((item) => item.userId));

  summary[today] = {
    toolId: TOOL_ID,
    toolName: TOOL_NAME,
    date: today,
    timezone: TIMEZONE,
    updatedAt: submittedAt,

    totalMembers: allMemberIds.length,
    submittedMembers: submittedTodayIds.size,
    missingMembers: Math.max(allMemberIds.length - submittedTodayIds.size, 0),
    submissionRate:
      allMemberIds.length > 0
        ? Math.round((submittedTodayIds.size / allMemberIds.length) * 100)
        : 0,

    members: {}
  };

  for (const userId of allMemberIds) {
    const member = membersById[userId];
    const userSubmission = submittedToday
      .filter((item) => item.userId === userId)
      .sort((a, b) => new Date(b.submittedAt) - new Date(a.submittedAt))[0];

    summary[today].members[userId] = {
      memberName: member.memberName,
      userId,
      status: userSubmission ? "submitted" : "missing",
      submittedAt: userSubmission ? userSubmission.submittedAt : null,
      submissionCountToday: submittedToday.filter((item) => item.userId === userId).length
    };
  }

  writeJson(submissionsPath, submissions);
  writeJson(summaryPath, summary);

  console.log("Tracking updated successfully.");
}

main();
