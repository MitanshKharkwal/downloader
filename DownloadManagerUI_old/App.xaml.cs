using Microsoft.UI.Xaml;

// To learn more about WinUI, the WinUI project structure,
// and more about our project templates, see: http://aka.ms/winui-project-info.

namespace DownloadManagerUI;

/// <summary>
/// Provides application-specific behavior to supplement the default Application class.
/// </summary>
public partial class App : Application
{
    private Window? _window;

    /// <summary>
    /// Initializes the singleton application object.  This is the first line of authored code
    /// executed, and as such is the logical equivalent of main() or WinMain().
    /// </summary>
    public App()
    {
        InitializeComponent();
    }

    /// <summary>
    /// Invoked when the application is launched.
    /// </summary>
    /// <param name="args">Details about the launch request and process.</param>
    protected override void OnLaunched(Microsoft.UI.Xaml.LaunchActivatedEventArgs args)
    {
        var mainInstance = Microsoft.Windows.AppLifecycle.AppInstance.FindOrRegisterForKey("DownloadManagerUI_MainInstance");
        if (!mainInstance.IsCurrent)
        {
            var currentArgs = Microsoft.Windows.AppLifecycle.AppInstance.GetCurrent().GetActivatedEventArgs();
            mainInstance.RedirectActivationToAsync(currentArgs).GetAwaiter().GetResult();
            System.Diagnostics.Process.GetCurrentProcess().Kill();
            return;
        }

        mainInstance.Activated += (s, e) =>
        {
            if (_window != null)
            {
                // Ensure UI updates happen on UI thread
                _window.DispatcherQueue.TryEnqueue(() =>
                {
                    _window.Activate();
                    _window.AppWindow.Show();
                });
            }
        };

        try
        {
            Microsoft.Windows.AppNotifications.AppNotificationManager.Default.Register();
        }
        catch { }

        _window = new MainWindow();
        _window.Activate();
    }
}
