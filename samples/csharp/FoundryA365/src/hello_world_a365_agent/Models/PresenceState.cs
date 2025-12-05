namespace HelloWorldA365.Models;

public enum Availability
{
    Available,
    Busy,
    Away,
    DoNotDisturb
}

public enum PresenceActivity
{
    Available,
    InACall,
    InAConferenceCall,
    Away,
    Presenting
}

public sealed record PresenceState(
    Availability Availability,
    PresenceActivity Activity)
{
    public static PresenceState Available =>
        new(Availability.Available, PresenceActivity.Available);

    public static PresenceState BusyInCall =>
        new(Availability.Busy, PresenceActivity.InACall);

    public static PresenceState BusyInConferenceCall =>
        new(Availability.Busy, PresenceActivity.InAConferenceCall);

    public static PresenceState Away =>
        new(Availability.Away, PresenceActivity.Away);

    public static PresenceState DoNotDisturbPresenting =>
        new(Availability.DoNotDisturb, PresenceActivity.Presenting);
}