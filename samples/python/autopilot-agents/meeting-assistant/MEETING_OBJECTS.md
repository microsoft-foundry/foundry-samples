# Meeting objects, identifiers, and ActivityProtocol payloads

This document maps the objects this sample encounters from the calendar event through
the transcript-backed report. The Autopilot receives Teams Activities as
ActivityProtocol payloads at `/activity/messages`, not Microsoft Graph
subscription notifications.

The tables describe expected payload fields and object relationships, distinguishing
**used by the sample**, **present but unused**, and **available through an API but
not requested**. The object map lists the resources and artifacts the sample
works through after receiving an Activity.
The transcript-ready XML example is abbreviated and synthetic.

## 1. Object map

These objects form relationships rather than one strict containment hierarchy. For
a recurring scheduled meeting, the calendar can contain multiple event instances
that point through the same join URL to a persistent Graph `onlineMeeting` and
meeting chat. Each time participants use that meeting, Teams creates an actual
call. Graph exposes the resulting transcripts under the persistent
`onlineMeeting`, while each transcript's `callId` identifies the actual call that
produced it.

```text
Calendar series
├── Event occurrence ───────┐
├── Event occurrence ───────┼── shared join URL
└── Event exception ────────┘          │
                                      ▼
                           Graph onlineMeeting
                           ├── chatInfo.threadId ──► meeting chat
                           └── transcripts
                               ├── callId: actual call A
                               └── callId: actual call B
```

An **occurrence** follows the calendar series without instance-specific changes.
An **exception** is an instance edited separately from the series, such as one
with a changed time or agenda. Its unchanged properties continue to inherit from
the series. Reading the selected event's `body.content` therefore returns the
effective agenda for either kind of instance.

Non-recurring meetings use a `singleInstance` calendar event. The sample queries
the agent user's default calendar through `calendarView`, which expands recurring
meetings into occurrences and exceptions and also returns single instances. It
does not retrieve a series master or merge its body with an instance body itself.
Event `type`, `seriesMasterId`, and `iCalUId` are not requested or used in selection.
See [calendarView][calendar-view].

The calendar event is not the parent of a call or transcript. It supplies the
scheduled slot and agenda. Likewise, the persistent chat is where participants
join and see meeting artifacts, but the Graph `onlineMeeting`, not the chat, is
the transcript API parent:

```text
/me/onlineMeetings/{meeting_id}/transcripts/{transcript_id}
```

The `onlineMeeting` points directly to the chat:
`onlineMeeting.chatInfo.threadId` is the meeting chat's `chat.id`. The chat has
reverse association metadata in `chat.onlineMeetingInfo`, including
`calendarEventId`, `joinWebUrl`, and the organizer, but it does not expose the
Graph `onlineMeeting.id`. The sample therefore verifies the direct pointer from
the resolved `onlineMeeting` to the incoming Activity's `conversation.id`; it
does not use `chat.onlineMeetingInfo`.
See [teamworkOnlineMeetingInfo][chat-meeting-info] for that reverse metadata.

The sample creates its own `Occurrence` record to correlate:

- the selected calendar single instance, occurrence, or exception and its agenda;
- the persistent Graph `onlineMeeting` and chat;
- the observed start and end of one actual call; and
- the call-specific transcripts used for that run's report.

| Object | Identity and pointers | Relationship and sample usage |
| --- | --- | --- |
| Calendar event: Graph `event` | Mailbox-specific `id`, scheduled `start` / `end`, and `body.content`; `type` is available but not requested. Its embedded `onlineMeeting` value contains the `joinUrl`. | The sample selects one single instance, occurrence, or exception from the agent user's default calendar by join URL and scheduled start, stores its `id` as `Occurrence.event_id`, and snapshots its effective agenda. The embedded join information is not the separate Graph `onlineMeeting` resource and does not supply that resource's `id`; its URL bridges the two lookups. See [event][event]. |
| Meeting chat: Graph `chat` | Graph chat `id`; linked directly from Graph meeting `chatInfo.threadId` and from the incoming Activity's `conversation.id`. Its `onlineMeetingInfo` contains `calendarEventId`, `joinWebUrl`, and organizer metadata, but not the Graph `onlineMeeting.id`. | The persistent thread in which participants can join and see meeting artifacts and where the agent posts reminders, acknowledgments, and reports. The sample requires `chatInfo.threadId == conversation.id` before binding a meeting to this chat. It does not use `chat.onlineMeetingInfo`. See [chat][chat]. |
| Scheduled meeting resource: Graph `onlineMeeting` | `id`, `joinWebUrl`, `chatInfo.threadId`; also has scheduled times and participant information. | The persistent meeting resource resolved using the join URL. `chatInfo.threadId` points to the associated Graph chat. Its `id` becomes `Occurrence.meeting_id` and is the parent ID used in transcript API paths. Multiple actual calls can produce artifacts under the same meeting. See [Get onlineMeeting][online-meeting]. |
| Actual meeting call | Transcript/recording `callId`; readiness XML can carry `Identifiers/Id[@type='callId']/@value`. | One actual run of the meeting, which can begin whenever participants use the join surface rather than only at a calendar slot. The sample does not fetch a Graph `call` object. It binds the XML value to the observed start/end record and uses it to filter transcript metadata. |
| Transcript: Graph `callTranscript` | Its own `id`, persistent `meetingId`, actual-run `callId`, `contentCorrelationId`, `transcriptContentUrl`, `createdDateTime`, and `endDateTime`. | Graph lists transcripts beneath the `onlineMeeting`, but `callId` distinguishes the actual call that produced each segment. A call can have multiple transcript segments. The sample selects the appropriate segments and reads each segment's WebVTT content using Graph meeting and transcript IDs. That UTF-8 content, rather than the XML notification or video, is the model's source text. See [callTranscript][transcript]. |
| OneDrive / SharePoint storage objects | A drive has a `driveId`; an item is addressed by its drive and item ID. Readiness XML advertises `driveId`, `driveItemId`, a transcript-item `id`, and a video-item viewer `uri`. | Storage identities are a separate namespace from Graph meeting-artifact identities. The sample does not use these IDs for API reads. It validates and stores the HTTPS SharePoint viewer URL as a human-facing citation destination; with multiple transcript segments, it instead links to the meeting chat's Recap. See [driveItem][drive-item]. |

Nested values in the map, including `event.onlineMeeting` and
`onlineMeeting.chatInfo`, belong to one owning Graph resource and are described on
that resource's row. Meeting-specific Activity payloads are documented separately
in Section 2.

## 2. Which pointers arrive on the ActivityProtocol payloads?

These are the four inbound Activity types on which the sample acts. Other
Activities, including ordinary chat messages and recording-only notifications,
do not initiate meeting analysis.

| Pointer | Agent added (`conversationUpdate`) | Meeting start (`event`) | Meeting end (`event`) | Transcript ready (`message` with XML) |
| --- | --- | --- | --- | --- |
| Meeting chat | `conversation.id` | `conversation.id` | `conversation.id` | `conversation.id` |
| Teams meeting context | `channelData.meeting.id`, required by the membership selector | `channelData.meeting.id` may be present but is not required by sample business logic; `value.Id` is SDK-validated and checked for nonblank text | Same as start | `channelData.meeting.id` may be present but is not required by the readiness selector or used for artifact lookup |
| Meeting join URL | Not supplied by the membership fields used here | `value.JoinUrl` | `value.JoinUrl` | Not supplied by the XML fields used here |
| Actual lifecycle time | No meeting-start/end time used | `value.StartTime` | `value.EndTime` | `RecordingContent/@timestamp`, interpreted by the sample as recording start |
| Mailbox calendar event ID | Not supplied | Not supplied; obtained through calendar lookup | Not supplied; uses persisted state | Not supplied; uses persisted state |
| Graph online-meeting ID | Not supplied | Resolved from join URL, not taken from `value.Id` | Uses stored binding | Uses stored binding |
| Actual call ID | No field used | Not present in start `value` | Not present in end `value` | `Identifiers/Id[@type='callId']/@value`, used when nonblank |
| Graph transcript ID | Not supplied | Not supplied | Not supplied | Obtained through transcript listing |
| Human-facing viewer URL | No field used | No field used | No field used | Video item's `uri`, validated and stored if suitable |

### Agent added to the meeting chat

See the Teams [Members added documentation and payload example](https://learn.microsoft.com/en-us/microsoftteams/platform/bots/how-to/conversations/subscribe-to-conversation-events#members-added)
for the `conversationUpdate` format.

`is_added_to_meeting` requires the recipient to appear in `membersAdded` and
requires meeting context. Missing channel data is ignored, not treated as a
meeting addition. `on_added_to_meeting` reads `/chats/{conversation.id}` to obtain
the title and posts a greeting. It does not resolve the calendar event, snapshot an
agenda, or create an `Occurrence`.

### Meeting start and end

The SDK routes these named events and provides native `MeetingStartEventValue`
or `MeetingEndEventValue` objects.

See the Teams [meeting start payload example](https://learn.microsoft.com/en-us/microsoftteams/platform/apps-in-teams-meetings/meeting-apps-apis#example-of-meeting-start-event-payload)
and [meeting end payload example](https://learn.microsoft.com/en-us/microsoftteams/platform/apps-in-teams-meetings/meeting-apps-apis#example-of-meeting-end-event-payload)
for `application/vnd.microsoft.meetingStart` and
`application/vnd.microsoft.meetingEnd`.

The pinned SDK expects the documented Pascal-case `value` fields. Camel-case-only
payloads are rejected by the native models; adding lower-case extra fields does
not override the Pascal-case values. Code consumes the native model fields `id`,
`title`, `meeting_type`, `join_url`, `start_time`, and `end_time`. The sample
requires nonblank ID/title/type/join URL, `MeetingType == "Scheduled"`, an
offset-aware lifecycle time, and a conversation ID. The type comparison ignores
surrounding whitespace; the stored join URL is also trimmed.
Neither `value.Id` nor the title is used to select or persist the Graph meeting.

At start, the join URL resolves the Graph meeting and selects the calendar event.
The run is saved even when the event has no explicit agenda; in that case no
reminder, end acknowledgment, transcript reads, or closure report is produced.
At end, chat ID, join URL, and end time match a stored unfinished run.
The end handler stores `ended_at` and posts an acknowledgment when an agenda
exists. **It does not read transcripts.**

### Transcript-ready message

The Activity has `type="message"` and XML in `text`. This is a separate format
from [Graph transcript change notifications][graph-notifications]. The parser
requires `URIObject/@type="Video.2/CallRecording.1"`, `RecordingStatus/@status`
equal to `Success`, and `Transcript` among the `RecordingContent/@contentTypes`.
The trimmed text must start with `<URIObject`, be at most 64,000 characters, and
contain neither `<!DOCTYPE` nor `<!ENTITY`. Malformed XML, missing chat/timestamp,
and timestamps without a timezone offset are rejected.

```xml
<URIObject type="Video.2/CallRecording.1">
  <RecordingStatus status="Success" />
  <Identifiers>
    <Id type="callId" value="actual-call-id" />
  </Identifiers>
  <RecordingContent contentTypes="Recording+Transcript"
                    timestamp="2026-10-01T14:01:00Z">
    <item type="onedriveForBusinessVideo"
          uri="https://contoso.sharepoint.com/recording-viewer" />
  </RecordingContent>
</URIObject>
```

The example includes only fields the parser consumes. The viewer URI is
synthetic; the sample stores it as a report source link.

| XML path, relative to `URIObject` | Pointer or metadata | Sample treatment |
| --- | --- | --- |
| `@type` | Notification artifact type. | Must equal `Video.2/CallRecording.1`. |
| `Identifiers/Id[@type='callId']/@value` | Actual call identifier. | Trimmed and stored as `RecordingAvailable.call_id`; absent/blank supplies no new binding. Transcript selection falls back to timestamps only when the occurrence has no stored call ID. |
| `RecordingContent/@timestamp` | Recording timestamp carried by the notification. | Parsed as an offset-aware recording-start time, stored in `RecordingAvailable.started_at`, and matched against observed start/end times. |
| `RecordingContent/@contentTypes` | Artifact types reported ready. | Must include `Transcript`; recording-only messages do not trigger transcript reads. |
| `RecordingStatus/@status` | Processing status. | Only `Success` is accepted; chunk/intermediate statuses are ignored. |
| `RecordingContent/item[@type='onedriveForBusinessVideo']/@uri` | SharePoint viewer pointer. | If a valid HTTPS SharePoint URL, stored as `viewer_url` for citations. It is not used to download video or transcript text. |

`RecordingAvailable` contains only `chat_id`, `started_at`, optional `viewer_url`,
and optional `call_id`. The notification must uniquely match an observed run in
that chat, and the run must already have an observed end. Pre-end readiness is
ignored without saving its call ID or viewer URL. A later contradictory call ID
is rejected rather than replacing the established binding.

Occurrence matching still requires the XML timestamp even when a call ID is
present; the call ID does not bypass the observed-start/end check. A later
notification without a call ID retains any previously bound call ID. A suitable
later viewer URL can replace the stored URL, but an absent or invalid URL does
not clear it. No transcript list or content is persisted from the notification.

Previously observed notifications used an organizer/recording initiator identity,
not a distinct system-only sender. This is an observation, not a guaranteed sender
contract. The sample does not authenticate readiness using ordinary sender fields.

## 3. How the sample follows these pointers

These are relative Work IQ resource paths. `fetch` supplies metadata;
`fetch_blob` supplies transcript bytes. IDs and query values below are symbolic;
the client performs URL encoding and OData string escaping.

| Step | Lookup / pointers | Result used |
| --- | --- | --- |
| Greeting | `fetch /chats/{chat_id}` | Confirm returned chat `id`; use `topic` for the greeting. |
| Bind start to Graph meeting | `fetch /me/onlineMeetings?$filter=JoinWebUrl eq '{join_url}'&$select=id,chatInfo,joinWebUrl` | Require a complete result with exactly one matching `chatInfo.threadId`; store its Graph `id`. |
| Find the calendar event | `fetch /me/calendarView?startDateTime={actual_start_minus_one_day}&endDateTime={actual_start_plus_one_day}&$select=id,subject,start,end,organizer,isOnlineMeeting,onlineMeeting,webLink` | Keep events with truthy `isOnlineMeeting`, the exact `onlineMeeting.joinUrl`, and scheduled start within 12 hours before or after actual start; require exactly one candidate and no next page. |
| Read agenda | `fetch /me/events/{event_id}?$select=id,subject,body,start,end,organizer,attendees,onlineMeeting,webLink` | Recheck join URL; extract explicit agenda items from `body.content` and save the snapshot. |
| Bind end | Stored chat ID + join URL + unfinished start within 24 hours before end | Save actual `ended_at`; do not list or fetch artifacts yet. |
| Bind readiness | Chat ID + XML recording timestamp inside the observed run's start/end interval | Store optional call ID/viewer URL only after the end has been observed. |
| Recheck Graph meeting | Repeat join-URL resolution and chat-thread check | Require the Graph meeting `id` to match the persisted binding. |
| List call-specific transcripts | `fetch /me/onlineMeetings/{meeting_id}/transcripts?$filter=callId eq '{call_id}'&$select=id,callId` | Check returned `callId` values, exclude other calls, and select matching Graph transcript IDs without timestamp matching. Missing returned call identity is an error. |
| Legacy transcript selection | When no call ID is bound: same transcript collection with `$select=id,createdDateTime,endDateTime` | Match `endDateTime`, or `createdDateTime` when end is absent, from observed start through observed end plus five minutes. |
| Read each selected segment | `fetch_blob /me/onlineMeetings/{meeting_id}/transcripts/{transcript_id}/content?$format=text/vtt` | Validate content type, byte count, Base64, and UTF-8; give the resulting transcript text to analysis. |
| Render and post | Source key `transcript:{Graph transcript id}` + application-selected viewer/chat URL | Render readable source labels and post the agenda closure report into the original conversation. |

All collection reads request `$top=100`, do not follow pagination, and expose a
next-page indicator. Call-specific transcript results still require one complete
page. The sample supports at most eight selected segments and 120,000 aggregate
transcript characters; it does not intentionally report on a partial collection.

Calendar selection is not a nearest-event search: two candidates inside the
12-hour window cause an error. An offset-aware scheduled start is accepted;
without an offset, only `UTC` or `Etc/UTC` is accepted as its `timeZone`.
The full-event read rechecks the join URL but does not recheck the scheduled start.
Selected event fields `subject`, `end`, `organizer`, `attendees`, and `webLink`
are not used to extract the agenda or authenticate the notification. Only
`body.content` is sent to the agenda model; explicit items are not inferred from
the title. The sample does not request or check `isCancelled` or attendee response
status.

For scheduled meetings, [direct transcript reads][get-transcript] require the
**Graph meeting ID and Graph transcript ID**. The call ID narrows the listing; it
does not replace either path parameter. The documented `/adhocCalls/{callId}`
paths are a different API scope and are not this sample's scheduled-meeting path.

The expected contract is that the readiness XML call ID identifies the same call
as Graph `callTranscript.callId`. The sample uses `callId eq ...` to
[list that call's transcripts][list-transcripts] and checks the returned call IDs.
A rejected filter is surfaced without silently retrying an unfiltered historical
read.

Graph documents `$filter` support on the transcript-list route, but live Work IQ
server-side filtering and XML-to-Graph call-ID equality with agent credentials
remain unverified. Offline tests cover the requested predicate and returned-ID
checks; they do not establish that live contract.

Graph exposes `meetingId`, `contentCorrelationId`, and `transcriptContentUrl`
on transcript resources, but the sample's metadata `$select` does not request
them. It uses the already-bound meeting ID and constructs the documented content
path. It does not infer a Graph transcript ID from XML storage IDs or opaque-ID
encoding, and does not implement recording/transcript correlation via
`contentCorrelationId`.

[event]: https://learn.microsoft.com/en-us/graph/api/resources/event?view=graph-rest-1.0
[calendar-view]: https://learn.microsoft.com/en-us/graph/api/calendar-list-calendarview?view=graph-rest-1.0
[chat]: https://learn.microsoft.com/en-us/graph/api/resources/chat?view=graph-rest-1.0
[chat-meeting-info]: https://learn.microsoft.com/en-us/graph/api/resources/teamworkonlinemeetinginfo?view=graph-rest-1.0
[online-meeting]: https://learn.microsoft.com/en-us/graph/api/onlinemeeting-get?view=graph-rest-1.0
[transcript]: https://learn.microsoft.com/en-us/graph/api/resources/calltranscript?view=graph-rest-1.0
[drive-item]: https://learn.microsoft.com/en-us/graph/api/resources/driveitem?view=graph-rest-1.0
[list-transcripts]: https://learn.microsoft.com/en-us/graph/api/onlinemeeting-list-transcripts?view=graph-rest-1.0
[get-transcript]: https://learn.microsoft.com/en-us/graph/api/calltranscript-get?view=graph-rest-1.0
[graph-notifications]: https://learn.microsoft.com/en-us/graph/teams-changenotifications-callrecording-and-calltranscript
