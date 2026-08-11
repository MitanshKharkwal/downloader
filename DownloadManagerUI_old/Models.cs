using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Runtime.CompilerServices;
using System.Text.Json.Serialization;

namespace DownloadManagerUI.Models;

public class DownloadTask : INotifyPropertyChanged
{
    private string _status = "PENDING";
    private long _downloadedBytes;
    private long _totalBytes;
    private double _speedBps;
    private string _error = "";

    [JsonPropertyName("id")]
    public string Id { get; set; } = "";
    private string _source = "";
    [JsonPropertyName("source")]
    public string Source
    {
        get => _source;
        set
        {
            if (SetProperty(ref _source, value))
            {
                OnPropertyChanged(nameof(Filename));
            }
        }
    }
    [JsonPropertyName("priority")]
    public int Priority { get; set; } = 1;
    private string _filePath = "";
    
    [JsonPropertyName("file_path")]
    public string FilePath
    {
        get => _filePath;
        set
        {
            if (SetProperty(ref _filePath, value))
            {
                OnPropertyChanged(nameof(Filename));
            }
        }
    }
    
    public string Filename
    {
        get
        {
            var name = System.IO.Path.GetFileName(_filePath);
            return string.IsNullOrEmpty(name) ? Source : name;
        }
    }

    [JsonPropertyName("status")]
    public string Status
    {
        get => _status;
        set => SetProperty(ref _status, value);
    }

    [JsonPropertyName("downloaded_bytes")]
    public long DownloadedBytes
    {
        get => _downloadedBytes;
        set { if (SetProperty(ref _downloadedBytes, value)) { OnPropertyChanged(nameof(Progress)); OnPropertyChanged(nameof(ProgressText)); OnPropertyChanged(nameof(SizeText)); OnPropertyChanged(nameof(ETAText)); } }
    }

    [JsonPropertyName("total_bytes")]
    public long TotalBytes
    {
        get => _totalBytes;
        set { if (SetProperty(ref _totalBytes, value)) { OnPropertyChanged(nameof(Progress)); OnPropertyChanged(nameof(ProgressText)); OnPropertyChanged(nameof(SizeText)); OnPropertyChanged(nameof(ETAText)); } }
    }

    [JsonPropertyName("speed_bps")]
    public double SpeedBps
    {
        get => _speedBps;
        set { if (SetProperty(ref _speedBps, value)) { OnPropertyChanged(nameof(SpeedText)); OnPropertyChanged(nameof(ETAText)); } }
    }

    [JsonPropertyName("error")]
    public string Error
    {
        get => _error;
        set { if (SetProperty(ref _error, value)) OnPropertyChanged(nameof(ErrorVisibility)); }
    }

    private string _description = "";
    [JsonPropertyName("description")]
    public string Description
    {
        get => _description;
        set => SetProperty(ref _description, value);
    }

    public string Q => "";
    public string LastTryDate => "";

    private double _createdAt;
    [JsonPropertyName("created_at")]
    public double CreatedAt
    {
        get => _createdAt;
        set { if (SetProperty(ref _createdAt, value)) OnPropertyChanged(nameof(DateAdded)); }
    }

    public string DateAdded
    {
        get
        {
            if (_createdAt <= 0) return "";
            var dateTime = DateTimeOffset.FromUnixTimeSeconds((long)_createdAt).ToLocalTime();
            return dateTime.ToString("yyyy-MM-dd HH:mm");
        }
    }

    private string _category = "Other";
    [JsonPropertyName("category")]
    public string Category
    {
        get => _category;
        set => SetProperty(ref _category, value);
    }

    public Microsoft.UI.Xaml.Visibility ErrorVisibility => string.IsNullOrEmpty(Error) ? Microsoft.UI.Xaml.Visibility.Collapsed : Microsoft.UI.Xaml.Visibility.Visible;

    public double Progress
    {
        get
        {
            if (TotalBytes == 0) return 0;
            return (double)DownloadedBytes / TotalBytes * 100.0;
        }
    }

    public string ProgressText => $"{Progress:F1}%";

    public string SizeText
    {
        get
        {
            if (TotalBytes == 0) return FormatBytes(DownloadedBytes);
            return $"{FormatBytes(DownloadedBytes)} / {FormatBytes(TotalBytes)}";
        }
    }

    public string SpeedText => SpeedBps > 0 ? $"{FormatBytes((long)SpeedBps)}/s" : "";

    public string ETAText
    {
        get
        {
            if (SpeedBps <= 0 || TotalBytes == 0 || DownloadedBytes >= TotalBytes || Status != "DOWNLOADING") return "";
            var remainingBytes = TotalBytes - DownloadedBytes;
            var seconds = (double)remainingBytes / SpeedBps;
            if (seconds > 3600) return $"{(int)(seconds / 3600)}h {((int)seconds % 3600) / 60}m";
            if (seconds > 60) return $"{(int)(seconds / 60)}m {(int)(seconds % 60)}s";
            return $"{(int)seconds}s remaining";
        }
    }

    private static string FormatBytes(long bytes)
    {
        string[] suffixes = { "B", "KB", "MB", "GB", "TB" };
        int counter = 0;
        decimal number = bytes;
        while (Math.Round(number / 1024) >= 1)
        {
            number = number / 1024;
            counter++;
        }
        return $"{number:n1} {suffixes[counter]}";
    }

    public event PropertyChangedEventHandler? PropertyChanged;
    protected void OnPropertyChanged([CallerMemberName] string? propertyName = null)
        => PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(propertyName));

    protected bool SetProperty<T>(ref T field, T value, [CallerMemberName] string? propertyName = null)
    {
        if (EqualityComparer<T>.Default.Equals(field, value)) return false;
        field = value;
        OnPropertyChanged(propertyName);
        return true;
    }
}


public class AppConfig
{
    [JsonPropertyName("download_dir")]
    public string DownloadDir { get; set; } = "";

    [JsonPropertyName("max_concurrent_downloads")]
    public int MaxConcurrentDownloads { get; set; } = 3;

    [JsonPropertyName("global_bandwidth_limit")]
    public int GlobalBandwidthLimit { get; set; } = 0;
}

public class VideoFormat
{
    [JsonPropertyName("format_id")]
    public string FormatId { get; set; } = "";

    [JsonPropertyName("ext")]
    public string Ext { get; set; } = "";

    [JsonPropertyName("resolution")]
    public string Resolution { get; set; } = "";

    [JsonPropertyName("filesize")]
    public long Filesize { get; set; } = 0;

    [JsonPropertyName("vcodec")]
    public string VCodec { get; set; } = "";

    [JsonPropertyName("acodec")]
    public string ACodec { get; set; } = "";

    [JsonPropertyName("format_note")]
    public string FormatNote { get; set; } = "";

    public string DisplayText
    {
        get
        {
            var size = Filesize > 0 ? $" ({Filesize / 1024 / 1024} MB)" : "";
            var codecInfo = "";
            if (VCodec != "none" && ACodec != "none") codecInfo = "[Video + Audio]";
            else if (VCodec != "none") codecInfo = "[Video Only]";
            else if (ACodec != "none") codecInfo = "[Audio Only]";

            return $"{Resolution} - {Ext} {codecInfo} - {FormatNote}{size}";
        }
    }
}

public class ColumnConfig
{
    public string Header { get; set; } = "";
    public bool IsVisible { get; set; } = true;
    public int DisplayIndex { get; set; }
    public double Width { get; set; }
}

public static class SettingsManager
{
    private static string GetConfigPath()
    {
        var dir = System.IO.Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), ".download_manager");
        System.IO.Directory.CreateDirectory(dir);
        return System.IO.Path.Combine(dir, "columns.json");
    }

    public static List<ColumnConfig> GetColumnConfigs()
    {
        try
        {
            var path = GetConfigPath();
            if (System.IO.File.Exists(path))
            {
                var jsonStr = System.IO.File.ReadAllText(path);
                var options = new System.Text.Json.JsonSerializerOptions { PropertyNameCaseInsensitive = true, TypeInfoResolver = new System.Text.Json.Serialization.Metadata.DefaultJsonTypeInfoResolver() };
                return System.Text.Json.JsonSerializer.Deserialize<List<ColumnConfig>>(jsonStr, options) ?? GetDefaultColumnConfigs();
            }
        }
        catch { }
        return GetDefaultColumnConfigs();
    }

    public static void SaveColumnConfigs(List<ColumnConfig> configs)
    {
        try
        {
            var options = new System.Text.Json.JsonSerializerOptions { TypeInfoResolver = new System.Text.Json.Serialization.Metadata.DefaultJsonTypeInfoResolver() };
            var json = System.Text.Json.JsonSerializer.Serialize(configs, options);
            System.IO.File.WriteAllText(GetConfigPath(), json);
        }
        catch { }
    }

    private static List<ColumnConfig> GetDefaultColumnConfigs()
    {
        return new List<ColumnConfig>
        {
            new ColumnConfig { Header = "File Name", IsVisible = true, DisplayIndex = 0, Width = 250 },
            new ColumnConfig { Header = "Q", IsVisible = true, DisplayIndex = 1, Width = 50 },
            new ColumnConfig { Header = "Size", IsVisible = true, DisplayIndex = 2, Width = 120 },
            new ColumnConfig { Header = "Status", IsVisible = true, DisplayIndex = 3, Width = 100 },
            new ColumnConfig { Header = "Progress", IsVisible = true, DisplayIndex = 4, Width = 150 },
            new ColumnConfig { Header = "Time left", IsVisible = true, DisplayIndex = 5, Width = 120 },
            new ColumnConfig { Header = "Transfer rate", IsVisible = true, DisplayIndex = 6, Width = 100 },
            new ColumnConfig { Header = "Last Try Date", IsVisible = true, DisplayIndex = 7, Width = 120 },
            new ColumnConfig { Header = "Description", IsVisible = true, DisplayIndex = 8, Width = 150 },
            new ColumnConfig { Header = "Date Added", IsVisible = true, DisplayIndex = 9, Width = 120 },
            new ColumnConfig { Header = "Actions", IsVisible = true, DisplayIndex = 10, Width = 200 }
        };
    }
}
