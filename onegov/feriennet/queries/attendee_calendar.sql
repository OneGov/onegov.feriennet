/*
    Basis for the attendee calendar
*/
SELECT
    periods.title as period,        -- Text
    periods.confirmed as confirmed, -- Boolean
    activities.title,               -- Text
    occasion_dates.start,           -- UTCDateTime
    occasion_dates.end,             -- UTCDateTime
    occasions.cancelled,            -- Boolean
    bookings.attendee_id,           -- UUID
    bookings.state                  -- Text

FROM
    occasion_dates
LEFT JOIN
    bookings
    ON occasion_dates.occasion_id = bookings.occasion_id
LEFT JOIN
    occasions
    ON occasion_dates.occasion_id = occasions.id
LEFT JOIN
    periods
    ON bookings.period_id = periods.id
LEFT JOIN
    activities
    ON occasions.activity_id = activities.id

ORDER BY
    attendee_id,
    occasion_dates.start

