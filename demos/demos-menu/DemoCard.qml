import QtQuick
import QtQuick.Controls
import QtQuick.Controls.Material
import QtQuick.Layouts

Rectangle {
    id: card

    property string demoName: ""
    property string demoDescription: ""
    property bool combinedArrayOnly: false    // hidden at model level — card never sees it
    property bool singleArrayOnly:   false    // gray when singleArray is false
    property bool disabled:          false    // always gray (under development)
    property string ip: ""
    property bool singleArray: false

    // Gray out if: disabled, single-array-only demo in multi-array mode, or no IP set.
    property bool meetsRequirements:
        !disabled &&
        !(singleArrayOnly && !singleArray) &&
        ip.length > 0

    signal launchRequested()

    width: 200
    height: 130
    radius: 8
    color: meetsRequirements ? "#2a3a44" : "#222a2f"
    border.color: meetsRequirements ? "#3a5a6a" : "#2a3238"
    opacity: meetsRequirements ? 1.0 : 0.5

    // Make the entire card tappable on touch screens.
    TapHandler {
        enabled: card.meetsRequirements
        onTapped: card.launchRequested()
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 14
        spacing: 6

        Label {
            text: card.demoName
            font.pixelSize: 14
            font.bold: true
            color: "#ffffff"
            elide: Text.ElideRight
            Layout.fillWidth: true
        }

        Label {
            text: card.demoDescription
            font.pixelSize: 11
            color: "#9fb3c8"
            wrapMode: Text.WordWrap
            maximumLineCount: 3
            elide: Text.ElideRight
            Layout.fillWidth: true
            Layout.fillHeight: true
        }

        RowLayout {
            Layout.fillWidth: true

            // Badge: shown only for single-array-only demos (as a hint to the user).
            Rectangle {
                radius: 3
                color: "#1a3a2a"
                visible: card.singleArrayOnly
                implicitWidth: badgeLabel.implicitWidth + 8
                implicitHeight: badgeLabel.implicitHeight + 4
                Label {
                    id: badgeLabel
                    anchors.centerIn: parent
                    text: "single-only"
                    font.pixelSize: 9
                    color: "#5add8a"
                }
            }

            Button {
                text: "Launch"
                enabled: card.meetsRequirements
                font.pixelSize: 12
                implicitHeight: 28
                Layout.fillWidth: true
                onClicked: card.launchRequested()

                ToolTip.visible: !card.meetsRequirements && hovered
                ToolTip.delay: 400
                ToolTip.text: {
                    if (card.disabled)
                        return "This demo is not yet available"
                    if (card.singleArrayOnly && !card.singleArray)
                        return "Requires single-array mode"
                    if (card.ip.length === 0)
                        return "Configure the ESPARGOS IP address first"
                    return ""
                }
            }
        }
    }
}
