import 'package:flutter/material.dart';
import 'package:phosphor_icons/phosphor_icons.dart';

import '../models/download_task.dart';
import '../theme/app_theme.dart';

/// A nav entry: `category == null` means "All Downloads".
class NavItem {
  const NavItem({required this.label, required this.icon, this.category});

  final String label;
  final IconData icon;
  final TaskCategory? category;
}

final List<NavItem> kNavItems = <NavItem>[
  NavItem(label: 'All Downloads', icon: PhosphorIcons.download(PhosphorIconsStyle.light)),
  NavItem(
    label: 'Video',
    icon: PhosphorIcons.videoCamera(PhosphorIconsStyle.light),
    category: TaskCategory.video,
  ),
  NavItem(
    label: 'Music',
    icon: PhosphorIcons.musicNote(PhosphorIconsStyle.light),
    category: TaskCategory.music,
  ),
  NavItem(
    label: 'Programs',
    icon: PhosphorIcons.terminal(PhosphorIconsStyle.light),
    category: TaskCategory.programs,
  ),
  NavItem(
    label: 'Documents',
    icon: PhosphorIcons.fileText(PhosphorIconsStyle.light),
    category: TaskCategory.documents,
  ),
  NavItem(
    label: 'Compressed',
    icon: PhosphorIcons.archive(PhosphorIconsStyle.light),
    category: TaskCategory.compressed,
  ),
  NavItem(
    label: 'Photos',
    icon: PhosphorIcons.image(PhosphorIconsStyle.light),
    category: TaskCategory.photos,
  ),
  NavItem(
    label: 'Other',
    icon: PhosphorIcons.file(PhosphorIconsStyle.light),
    category: TaskCategory.other,
  ),
];

class Sidebar extends StatelessWidget {
  const Sidebar({
    super.key,
    required this.selected,
    required this.counts,
    required this.onSelect,
    required this.onNewDownload,
    required this.onSettings,
    this.collapsed = false,
  });

  /// Index into [kNavItems].
  final int selected;
  final Map<int, int> counts;
  final ValueChanged<int> onSelect;
  final VoidCallback onNewDownload;
  final VoidCallback onSettings;
  final bool collapsed;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: collapsed ? 72 : 248,
      decoration: const BoxDecoration(
        color: AppColors.background,
        border: Border(right: BorderSide(color: AppColors.border)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: <Widget>[
          _Brand(collapsed: collapsed),
          Padding(
            padding: EdgeInsets.symmetric(horizontal: collapsed ? 12 : 14),
            child: _NewDownloadButton(
              collapsed: collapsed,
              onPressed: onNewDownload,
            ),
          ),
          const SizedBox(height: 18),
          if (!collapsed)
            Padding(
              padding: const EdgeInsets.only(left: 24, bottom: 8),
              child: Text(
                'LIBRARY',
                style: Theme.of(context).textTheme.labelSmall?.copyWith(
                      color: AppColors.textMuted,
                      fontSize: 10,
                      letterSpacing: 1.1,
                    ),
              ),
            ),
          Expanded(
            child: SingleChildScrollView(
              padding: const EdgeInsets.symmetric(horizontal: 12),
              child: Stack(
                children: <Widget>[
                  AnimatedPositioned(
                    duration: const Duration(milliseconds: 200),
                    curve: Curves.easeInOutCubic,
                    top: selected * 38.0,
                    left: 0,
                    right: 0,
                    height: 36,
                    child: Container(
                      decoration: BoxDecoration(
                        color: AppColors.surfaceActive,
                        borderRadius: AppRadius.sm,
                      ),
                    ),
                  ),
                  Column(
                    children: List<Widget>.generate(kNavItems.length, (int index) {
                      return _SidebarTile(
                        item: kNavItems[index],
                        selected: index == selected,
                        count: counts[index] ?? 0,
                        collapsed: collapsed,
                        onTap: () => onSelect(index),
                      );
                    }),
                  ),
                ],
              ),
            ),
          ),
          const Divider(),
          Padding(
            padding: EdgeInsets.fromLTRB(12, 10, 12, 14),
            child: _SidebarTile(
              item: NavItem(
                label: 'Settings',
                icon: PhosphorIcons.gear(PhosphorIconsStyle.light),
              ),
              selected: false,
              count: 0,
              collapsed: collapsed,
              onTap: onSettings,
            ),
          ),
        ],
      ),
    );
  }
}

class _Brand extends StatelessWidget {
  const _Brand({required this.collapsed});

  final bool collapsed;

  @override
  Widget build(BuildContext context) {
    final Widget mark = Container(
      height: 26,
      width: 26,
      decoration: BoxDecoration(
        borderRadius: AppRadius.sm,
        gradient: const LinearGradient(
          colors: <Color>[AppColors.accent, Color(0xFF8B6CFA)],
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
        ),
      ),
      child: Icon(
        PhosphorIcons.arrowDown(PhosphorIconsStyle.light),
        size: 16,
        color: Colors.white,
      ),
    );

    return Padding(
      padding: EdgeInsets.fromLTRB(collapsed ? 23 : 26, 26, 20, 22),
      child: Row(
        children: <Widget>[
          mark,
          if (!collapsed) ...<Widget>[
            const SizedBox(width: 10),
            Text(
              'Fetchly',
              style: Theme.of(context).textTheme.titleMedium?.copyWith(
                    fontSize: 15,
                    color: AppColors.textPrimary,
                  ),
            ),
          ],
        ],
      ),
    );
  }
}

class _NewDownloadButton extends StatefulWidget {
  const _NewDownloadButton({required this.collapsed, required this.onPressed});

  final bool collapsed;
  final VoidCallback onPressed;

  @override
  State<_NewDownloadButton> createState() => _NewDownloadButtonState();
}

class _NewDownloadButtonState extends State<_NewDownloadButton> {
  bool _hovered = false;

  @override
  Widget build(BuildContext context) {
    return Tooltip(
      message: widget.collapsed ? 'New Download' : '',
      child: MouseRegion(
        cursor: SystemMouseCursors.click,
        onEnter: (_) => setState(() => _hovered = true),
        onExit: (_) => setState(() => _hovered = false),
        child: GestureDetector(
          onTap: widget.onPressed,
          child: AnimatedContainer(
            duration: AppTheme.fast,
            height: 38,
            alignment: Alignment.center,
            decoration: BoxDecoration(
              color: _hovered ? AppColors.accentHover : AppColors.accent,
              borderRadius: AppRadius.md,
            ),
            child: widget.collapsed
                ? Icon(PhosphorIcons.plus(PhosphorIconsStyle.light), size: 18, color: Colors.white)
                : Row(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: <Widget>[
                      Icon(
                        PhosphorIcons.plus(PhosphorIconsStyle.light),
                        size: 17,
                        color: Colors.white,
                      ),
                      const SizedBox(width: 7),
                      Text(
                        'New Download',
                        style:
                            Theme.of(context).textTheme.labelLarge?.copyWith(
                                  color: Colors.white,
                                  fontWeight: FontWeight.w600,
                                  fontSize: 13,
                                ),
                      ),
                    ],
                  ),
          ),
        ),
      ),
    );
  }
}

class _SidebarTile extends StatefulWidget {
  const _SidebarTile({
    required this.item,
    required this.selected,
    required this.count,
    required this.collapsed,
    required this.onTap,
  });

  final NavItem item;
  final bool selected;
  final int count;
  final bool collapsed;
  final VoidCallback onTap;

  @override
  State<_SidebarTile> createState() => _SidebarTileState();
}

class _SidebarTileState extends State<_SidebarTile> {
  bool _hovered = false;

  @override
  Widget build(BuildContext context) {
    final TextTheme text = Theme.of(context).textTheme;
    final Color fg = widget.selected
        ? AppColors.textPrimary
        : _hovered
            ? AppColors.textSecondary
            : AppColors.textMuted;
    final Color bg = _hovered && !widget.selected
        ? AppColors.surface
        : Colors.transparent;

    return Padding(
      padding: const EdgeInsets.only(bottom: 2),
      child: Tooltip(
        message: widget.collapsed ? widget.item.label : '',
        child: MouseRegion(
          cursor: SystemMouseCursors.click,
          onEnter: (_) => setState(() => _hovered = true),
          onExit: (_) => setState(() => _hovered = false),
          child: GestureDetector(
            onTap: widget.onTap,
            child: AnimatedContainer(
              duration: AppTheme.fast,
              height: 36,
              padding: EdgeInsets.symmetric(horizontal: widget.collapsed ? 0 : 10),
              alignment:
                  widget.collapsed ? Alignment.center : Alignment.centerLeft,
              decoration: BoxDecoration(color: bg, borderRadius: AppRadius.sm),
              child: widget.collapsed
                  ? Icon(widget.item.icon, size: 18, color: fg)
                  : Row(
                      children: <Widget>[
                        Icon(widget.item.icon, size: 17, color: fg),
                        const SizedBox(width: 10),
                        Expanded(
                          child: Text(
                            widget.item.label,
                            overflow: TextOverflow.ellipsis,
                            style: text.bodyMedium?.copyWith(
                              fontSize: 13,
                              fontWeight: widget.selected
                                  ? FontWeight.w600
                                  : FontWeight.w500,
                              color: fg,
                            ),
                          ),
                        ),
                        if (widget.count > 0)
                          Text(
                            '${widget.count}',
                            style: text.labelSmall?.copyWith(
                              color: widget.selected
                                  ? AppColors.textSecondary
                                  : AppColors.textMuted,
                              fontSize: 11,
                            ),
                          ),
                      ],
                    ),
            ),
          ),
        ),
      ),
    );
  }
}
