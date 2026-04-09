import QtQuick
import QtQuick.Controls
import QtQuick.Controls.Material
import QtQuick.Layouts

Rectangle {
    id: card

    property string demoName: ""
    property string demoDescription: ""
    property var requires: []
    property string ip: ""
    property bool singleArray: false

    property bool meetsRequirements: {
        if (requires.length === 0) return true
        if (requires.indexOf("single_array") >= 0 && ip.length === 0) return false
        if (requires.indexOf("multi_array") >= 0 && singleArray) return false
        return true
    }

    signal launchRequested()

    width: 200
    height: 130
    radius: 8
    color: meetsRequirements ? "#2a3a44" : "#222a2f"
    border.color: meetsRequirements ? "#3a5a6a" : "#2a3238"
    opacity: meetsRequirements ? 1.0 : 0.5

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

            // Requires badge
            Rectangle {
                radius: 3
                color: requires.indexOf("multi_array") >= 0 ? "#1a3a5a" : "#1a3a2a"
                visible: requires.length > 0
                implicitWidth: requiresLabel.implicitWidth + 8
                implicitHeight: requiresLabel.implicitHeight + 4
                Label {
                    id: requiresLabel
                    anchors.centerIn: parent
                    text: requires.indexOf("multi_array") >= 0 ? "multi" : "single"
                    font.pixelSize: 9
                    color: requires.indexOf("multi_array") >= 0 ? "#5aaddd" : "#5add8a"
                }
            }

            Item { Layout.fillWidth: true }

            Button {
                text: "Launch"
                enabled: card.meetsRequirements
                font.pixelSize: 12
                implicitHeight: 28
                onClicked: card.launchRequested()

                ToolTip.visible: !card.meetsRequirements && hovered
                ToolTip.delay: 400
                ToolTip.text: {
                    if (requires.indexOf("single_array") >= 0 && ip.length === 0)
                        return "Configure the ESPARGOS IP address first"
                    if (requires.indexOf("multi_array") >= 0 && singleArray)
                        return "Requires multi-array mode — disable single-array"
                    return ""
                }
            }
        }
    }
}
